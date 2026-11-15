# -*- coding: utf-8 -*-
"""Offline / admin step (NOT per-request): PRE-RENDER the enhanced served PDF for every servable
paper ONCE and store it at served/<id>.pdf, recording (served_object, served_filename) on
pending_papers. The bot then serves a fast GCS download instead of live-rendering (rasterize +
CLAHE + stitch) on every request — which kills both the per-serve render latency and the
concurrency OOM/SIGABRT risk (two heavy live renders overlapping aborts the worker even at 2Gi).

Reuses the EXACT live render (retrieval.precompute_served_pdf -> load_served_bytes_v1), so the
stored PDF is identical to what live-render produces today. Heavy + sequential by design (one render
at a time -> never OOMs); this is the one-time batch cost, not a per-request cost.

Servable id set (each unit ONCE): logical_exam_ids of grouped multi-page exams, PLUS student_visible
single rows that are not part of any group. Re-runnable: --skip-existing resumes (skips rows that
already have served_object). Run with the prod env (GCP_PROJECT / CLOUD_SQL_INSTANCE / GCS_BUCKET).

  python -m app.build_served_pdfs                 # render all (overwrites)
  python -m app.build_served_pdfs --skip-existing # resume: only rows missing served_object
  python -m app.build_served_pdfs --ids 854,967   # just these served ids (targeted backfill)
"""
import os
import sys
from sqlalchemy import text
from app.db import SessionLocal
from app.config import settings
from app.providers import get_object_store
from app import retrieval

MIGRATE = [
    "ALTER TABLE pending_papers ADD COLUMN IF NOT EXISTS served_object TEXT",
    "ALTER TABLE pending_papers ADD COLUMN IF NOT EXISTS served_filename TEXT",
]


def _servable_ids(s) -> list[int]:
    """Each servable unit exactly once: grouped exams keyed by logical_exam_id (lead row must be
    student_visible), plus student_visible singles not in any group."""
    grouped = s.execute(text(
        "SELECT DISTINCT eg.logical_exam_id AS sid FROM exam_group eg "
        "JOIN pending_papers pp ON pp.id = eg.logical_exam_id "
        "WHERE pp.student_visible AND pp.source = :src"
    ), {"src": settings.serve_source_tag}).scalars().all()
    singles = s.execute(text(
        "SELECT id AS sid FROM pending_papers pp WHERE pp.student_visible AND pp.source = :src "
        "AND NOT EXISTS (SELECT 1 FROM exam_group eg WHERE eg.page_row_id = pp.id)"
    ), {"src": settings.serve_source_tag}).scalars().all()
    return sorted(set(grouped) | set(singles))


def build(skip_existing: bool = False, only_ids: list[int] | None = None) -> None:
    s = SessionLocal()
    for ddl in MIGRATE:
        s.execute(text(ddl))
    s.commit()
    store = get_object_store(settings)

    ids = only_ids if only_ids else _servable_ids(s)
    if skip_existing and not only_ids:
        done = set(s.execute(text(
            "SELECT id FROM pending_papers WHERE served_object IS NOT NULL"
        )).scalars().all())
        ids = [i for i in ids if i not in done]

    # Cloud Run parallel-task sharding: each task processes a disjoint slice (index % count), so
    # --tasks N --parallelism N renders ~1/N each -> the whole corpus finishes in ~1/N the wall time.
    # Sequential WITHIN a task (one render at a time) keeps each container's memory bounded (no OOM).
    shard_i = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    shard_n = int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1"))
    if shard_n > 1:
        ids = [x for k, x in enumerate(ids) if k % shard_n == shard_i]
        print(f"shard {shard_i}/{shard_n}: {len(ids)} ids this task", flush=True)

    total = len(ids)
    print(f"pre-rendering {total} servable papers -> {settings.serve_precompute_prefix}<id>.pdf "
          f"(skip_existing={skip_existing})", flush=True)
    ok = fail = 0
    for n, sid in enumerate(ids, 1):
        try:
            obj, fn = retrieval.precompute_served_pdf(s, sid, store)
            s.commit()
            ok += 1
            if n % 25 == 0 or n == total:
                print(f"  [{n}/{total}] ok={ok} fail={fail}  last={sid} -> {obj}", flush=True)
        except Exception as e:
            s.rollback()
            fail += 1
            print(f"  [{n}/{total}] FAIL sid={sid}: {type(e).__name__}: {e}", flush=True)
    done_n = s.execute(text("SELECT count(*) FROM pending_papers WHERE served_object IS NOT NULL")).scalar()
    print(f"done: {ok} rendered, {fail} failed; pending_papers with served_object now = {done_n}", flush=True)
    s.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    skip = "--skip-existing" in args
    only = None
    if "--ids" in args:
        only = [int(x) for x in args[args.index("--ids") + 1].split(",") if x.strip()]
    build(skip_existing=skip, only_ids=only)
