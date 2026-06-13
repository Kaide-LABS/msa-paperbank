# -*- coding: utf-8 -*-
"""V1.2 multi-page exam grouping — the APPROVED diagnostic heuristic (frag_group.py) ported into
the app. DERIVED metadata only: it reads pending_papers and writes the exam_group side table;
page rows are never modified, and dropping exam_group is an instant, total rollback.

Heuristic (layered, conservative — better single pages than a Frankenstein exam):
  - IMAGE rows only (PDFs are already whole logical exams from the ingest splitter).
  - Candidate cluster = (folder, filename-doc-type), so an Exam and a CA in one folder split apart.
  - Folder is a REAL course folder iff filing_source in {slug,catalog,direct_code}; dept_fallback /
    plural catch-all folders ('Exams','CAs') are dumping grounds -> never grouped.
  - HIGH   = course folder, single real session, size 2..MAX, explicit page markers (page/pic/exam N)
  - MEDIUM = course folder, single real session, size 2..MAX, sequential counters/timestamps
  - LOW    = dump/catch-all folder, mixed CA+exam, oversized, or UUID/hash names (order unknown)
  - ATOMIC = single page
Phase 2a writes HIGH only; MEDIUM follows after the 2b ordering fix + re-diagnosis.
"""
import re
from collections import defaultdict
from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_PAGES = 10
COURSE_FILED = {"slug", "catalog", "direct_code"}
EXPLICIT = re.compile(r"(?:\bpage|\bpic|picture|\bexam|\bimg|image)\s*_?\s*(\d+)", re.I)
TRAIL = re.compile(r"(\d+)\D*$")
GENERIC_FOLDER = re.compile(r"^(copy of\s+)?(exams|ca'?s|past\s*questions?|past\s*papers?|pqs?|"
                            r"questions|tests|materials|documents|all|misc|others?)$", re.I)
UUID_RE = re.compile(r"^(copy of\s+)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
IMG_EXT = ("jpg", "jpeg", "heic", "png")


def _norm_session(s):
    s = (s or "").strip().lower()
    return s.upper() if s in ("ca1", "ca2") else ("exam" if s == "exam" else None)


def doc_type(fname):
    low = fname.lower()
    has_exam = bool(re.search(r"\bexam", low))
    has_ca = bool(re.search(r"\bca\b|\bca[\s_]*\d|continuous\s*assess", low))
    if has_ca and not has_exam:
        return "CA"
    if has_exam:
        return "exam"
    return "generic"


def order_class(members):
    stems = [m["fname"].rsplit(".", 1)[0] for m in members]
    if sum(1 for s in stems if UUID_RE.match(s.strip())) >= len(members) / 2:
        return "UNKNOWN"
    ex = [EXPLICIT.search(s) for s in stems]
    if all(e for e in ex) and len({int(e.group(1)) for e in ex}) == len(members):
        return "CONFIDENT"
    nums = [int(TRAIL.search(s).group(1)) if TRAIL.search(s) else None for s in stems]
    good = [n for n in nums if n is not None]
    if len(good) == len(members) and len(set(good)) >= max(2, len(members) - 1):
        return "SEQUENTIAL"
    return "UNKNOWN"


def _order_key(m):
    s = m["fname"].rsplit(".", 1)[0]
    e = EXPLICIT.search(s)
    t = TRAIL.search(s)
    num = int(e.group(1)) if e else (int(t.group(1)) if t else None)
    return (num is None, num if num is not None else 0, m["fname"])


def classify(rows):
    """rows: dicts with id, gcs_object, course_code, exam_session, filing_source.
    Returns clusters: dict(members=[ordered rows], conf, reason, size)."""
    R = []
    for r in rows:
        gobj = r["gcs_object"]
        folder, fname = (gobj.rsplit("/", 1) if "/" in gobj else ("", gobj))
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in IMG_EXT:
            continue
        R.append({**r, "folder": folder, "fname": fname})

    by_cluster = defaultdict(list)
    for x in R:
        by_cluster[(x["folder"], doc_type(x["fname"]))].append(x)

    clusters = []
    for (folder, _dt), members in by_cluster.items():
        base = folder.rsplit("/", 1)[-1].strip()
        course = sum(1 for m in members if m["filing_source"] in COURSE_FILED) >= (len(members) / 2)
        generic = bool(GENERIC_FOLDER.match(base))
        real_sessions = {_norm_session(m["exam_session"]) for m in members}
        real_sessions.discard(None)
        size = len(members)
        oc = order_class(members) if size >= 2 else "CONFIDENT"
        ordered = sorted(members, key=_order_key)

        if size == 1:
            conf, reason = "ATOMIC", "single page"
        elif not course or generic:
            conf, reason = "LOW", "catch-all/dump folder" if generic else "dump folder"
        elif len(real_sessions) > 1:
            conf, reason = "LOW", f"mixed sessions {sorted(real_sessions)}"
        elif size > MAX_PAGES:
            conf, reason = "LOW", f"oversized ({size})"
        elif oc == "UNKNOWN":
            conf, reason = "LOW", "order unknown (UUID/hash)"
        elif oc == "CONFIDENT":
            conf, reason = "HIGH", "explicit page order"
        else:
            conf, reason = "MEDIUM", "sequential order"
        clusters.append({"members": ordered, "conf": conf, "reason": reason, "size": size})
    return clusters


def build_exam_groups(session: Session, confidences=("HIGH",)):
    """(Re)build exam_group rows for the given confidence levels. Idempotent: clears those levels
    first. Returns (n_exams, n_pages)."""
    rows = session.execute(text(
        "SELECT id, gcs_object, course_code, exam_session, filing_source "
        "FROM pending_papers WHERE source='corpus_full' AND student_visible"
    )).mappings().all()
    clusters = classify([dict(r) for r in rows])

    session.execute(text("DELETE FROM exam_group WHERE grouping_confidence = ANY(:c)"),
                    {"c": list(confidences)})
    n_exams = n_pages = 0
    for cl in clusters:
        if cl["conf"] not in confidences or cl["size"] < 2:
            continue
        ids = [m["id"] for m in cl["members"]]
        lex = min(ids)
        for order, m in enumerate(cl["members"], 1):
            session.execute(text(
                "INSERT INTO exam_group (page_row_id, logical_exam_id, page_order, grouping_confidence) "
                "VALUES (:pid, :lex, :ord, :conf) "
                "ON CONFLICT (page_row_id) DO UPDATE SET logical_exam_id=:lex, page_order=:ord, "
                "grouping_confidence=:conf"
            ), {"pid": m["id"], "lex": lex, "ord": order, "conf": cl["conf"]})
        n_exams += 1
        n_pages += len(ids)
    session.commit()
    return n_exams, n_pages
