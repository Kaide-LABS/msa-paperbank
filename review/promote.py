# -*- coding: utf-8 -*-
"""Approve -> promote a contribution into the live corpus (student_visible); Deny -> close it.
Either way the contributor is notified via the bot's WhatsApp send path. The promotion path is the
ONLY way a contributed row becomes student_visible.

Promotion mirrors the corpus: copy page images to the served prefix, insert one student_visible
pending_papers row per page (source='corpus_full' so the live bot serves it unchanged;
contribution_id marks the contributed origin), and for multi-page write exam_group from the KNOWN
page_order (no inference). Dedup REPLACE retires the whole old logical paper (reversible:
student_visible=false, not deleted)."""
import hashlib
import logging
from sqlalchemy import text
from app.config import settings
from app import whatsapp

log = logging.getLogger(__name__)

_NOTIFY_APPROVED = "Your contribution was added — JazakAllah khair (may God reward you with good)!"


def _ext(obj: str) -> str:
    return obj.rsplit(".", 1)[-1].lower() if "." in obj else "jpg"


def promote(session, gcs, http, cid: int, filing: dict, dedup_choice: str, reviewer: str) -> int:
    """Returns the number of student-visible page-rows created."""
    contrib = session.execute(text(
        "SELECT contributor_phone, contributor_school, likely_dup_of FROM contributions WHERE id=:c"
    ), {"c": cid}).mappings().first()
    pages = session.execute(text(
        "SELECT gcs_object, page_order FROM contribution_pages WHERE contribution_id=:c ORDER BY page_order"
    ), {"c": cid}).mappings().all()
    school = contrib["contributor_school"]
    bucket = gcs.bucket(settings.gcs_bucket)

    new_ids = []
    for k, pg in enumerate(pages, 1):
        src = bucket.blob(pg["gcs_object"])
        dst_name = f"{settings.review_promoted_prefix}{cid}/{k}.{_ext(pg['gcs_object'])}"
        bucket.copy_blob(src, bucket, dst_name)            # served copy (raw contribution kept intact)
        sha = hashlib.sha256(f"contrib-{cid}-{k}-{dst_name}".encode()).hexdigest()[:32]
        nid = session.execute(text(
            "INSERT INTO pending_papers (source, sha, gcs_object, course_code, course_title, school, "
            "year, exam_session, outcome, curation_tier, filing_source, filing_confidence, "
            "student_visible, contribution_id) VALUES "
            "('corpus_full', :sha, :obj, :code, :title, :school, :year, :sess, 'approved_contribution', "
            "'reviewed', 'contributed', 'reviewed', true, :cid) RETURNING id"
        ), {"sha": sha, "obj": dst_name, "code": filing.get("course_code"), "title": filing.get("course_title"),
            "school": school, "year": filing.get("year"), "sess": filing.get("exam_session"), "cid": cid}).scalar()
        new_ids.append(nid)

    # multi-page -> exam_group from the KNOWN order (no inference needed)
    if len(new_ids) > 1:
        lex = min(new_ids)
        for order, pid in enumerate(new_ids, 1):
            session.execute(text(
                "INSERT INTO exam_group (page_row_id, logical_exam_id, page_order, grouping_confidence) "
                "VALUES (:pid, :lex, :o, 'reviewed') ON CONFLICT (page_row_id) DO NOTHING"
            ), {"pid": pid, "lex": lex, "o": order})

    # dedup REPLACE -> retire the whole old logical paper (reversible)
    if dedup_choice == "replace" and contrib["likely_dup_of"]:
        old = contrib["likely_dup_of"]
        lex = session.execute(text("SELECT logical_exam_id FROM exam_group WHERE page_row_id=:o"),
                              {"o": old}).scalar()
        if lex:
            session.execute(text("UPDATE pending_papers SET student_visible=false WHERE id IN "
                                 "(SELECT page_row_id FROM exam_group WHERE logical_exam_id=:l)"), {"l": lex})
        else:
            session.execute(text("UPDATE pending_papers SET student_visible=false WHERE id=:o"), {"o": old})

    session.execute(text(
        "UPDATE contributions SET status='approved', reviewed_by=:r, reviewed_at=now(), "
        "course_code=:code, course_title=:title, year=:year, exam_session=:sess, doc_type=:dt, "
        "updated_at=now() WHERE id=:c"
    ), {"r": reviewer, "code": filing.get("course_code"), "title": filing.get("course_title"),
        "year": filing.get("year"), "sess": filing.get("exam_session"), "dt": filing.get("doc_type"), "c": cid})
    session.commit()

    try:
        whatsapp.send_text(http, contrib["contributor_phone"], _NOTIFY_APPROVED)
    except Exception:
        log.exception("approve_notify_failed", extra={"cid": cid})
    return len(new_ids)


def deny(session, http, cid: int, comment: str | None, reviewer: str) -> None:
    contrib = session.execute(text("SELECT contributor_phone FROM contributions WHERE id=:c"),
                              {"c": cid}).mappings().first()
    session.execute(text(
        "UPDATE contributions SET status='denied', review_comment=:cm, reviewed_by=:r, reviewed_at=now(), "
        "updated_at=now() WHERE id=:c"
    ), {"cm": (comment or None), "r": reviewer, "c": cid})
    session.commit()
    if comment:
        body = f"Your contribution wasn't added.\nReason: {comment}"
    else:
        body = ("Your contribution wasn't added this time. JazakAllah khair (may God reward you with good) "
                "for contributing — please feel free to send clearer photos or another paper.")
    try:
        whatsapp.send_text(http, contrib["contributor_phone"], body)
    except Exception:
        log.exception("deny_notify_failed", extra={"cid": cid})
