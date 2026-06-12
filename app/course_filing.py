"""
Context-aware course-FILING deriver for index-mode routing.

The bare 2-4-letter-code regex left ~89% of corpus papers "unfilable" — but the path almost
always carries the dept + course title ("Introduction to Finance", "Gen. Chemistry 1"). This
deriver USES that: it always yields something FILABLE (an official code, a catalog code, or a
stable slug from dept+title), so only a genuinely malformed path (no dept and no title) is left
for a human. A consistent slug ("FIN-INTRODUCTION-TO-FINANCE") is far better for retrieval than
"unfilable" — and crucially we NEVER fabricate an official-looking code we're unsure of.

derive_filing(folder_path) -> {course_code, course_title, dept, confidence, source}
  layers (first confident hit wins):
    1. DIRECT CODE  — a real code token in the path ("ECO 213", "GST111", "CHM101"). high.
    2. CATALOG      — a curated title->official-code map for courses we're confident about
                      (e.g. "Communication in English"->GST111, "Gen. Chemistry"->CHM101). high.
       SLUG         — title present but not in the catalog -> stable dept+title slug. medium.
    3. DEPT FALLBACK— no title but a dept (and level) -> dept-level slug. low. (still filable)
    4. MALFORMED    — no dept and no title -> course_code None. none. (the only needs-human case)
"""
import re

# Departments seen in the corpus, ordered specific-first so "software engineering" beats
# "engineering" and "computer science" is caught before a bare "science".
_DEPTS = [
    ("software eng", "SWE", "Software Engineering"),
    ("data science", "DSC", "Data Science"),
    ("computer science", "CSC", "Computer Science"),
    ("information science", "ISMS", "Information Science and Media Studies"),
    ("isms", "ISMS", "Information Science and Media Studies"),
    ("mass comm", "MASSCOM", "Mass Communication"),
    ("film", "FILM", "Film and Multimedia Studies"),
    ("business admin", "BUSADMIN", "Business Administration"),
    ("accounting", "ACC", "Accounting"),
    ("economics", "ECON", "Economics"),
    ("finance", "FIN", "Finance"),
    ("engineering", "ENG", "Engineering"),
]

# Confident, university-wide title -> OFFICIAL code mappings only. Anything we are NOT sure of is
# left to the slug path (a wrong "FIN101" is worse than an honest slug).
GENERAL_CATALOG = {
    "communication in english": "GST111",
    "communications in english": "GST111",
    "comm in english": "GST111",
    "comm in english iii": "GST111",
    "general chemistry": "CHM101",
    "general chemistry i": "CHM101",
    "general chemistry 1": "CHM101",
    "general physics": "PHY101",
    "general physics i": "PHY101",
    "general physics 1": "PHY101",
    "general physics ii": "PHY102",
    "general physics 2": "PHY102",
}

_CODE = re.compile(r"\b([A-Z]{2,4})[\s\-]?(\d{2,3})\b")


def _segments(path):
    return [s for s in path.replace("\\", "/").split("/") if s]


def _match_dept(seg):
    n = seg.lower()
    for pat, code, name in _DEPTS:
        if pat in n:
            return code, name
    return None


def _level(seg):
    m = re.search(r"(\d)00\s*level", seg, re.I)
    if m:
        return m.group(1) + "00"
    m = re.search(r"year\s*(\d)", seg, re.I)
    if m:
        return str(int(m.group(1)) * 100)
    return None


def _is_structural(seg):
    n = seg.strip().lower()
    if re.search(r"\d00\s*level|year\s*\d|\blevel\b", n):
        return True
    if re.search(r"20\d{2}", n):           # academic-year folder
        return True
    if "semester" in n:
        return True
    if n in ("cas", "ca", "ca1", "ca2", "exam", "examination", "session"):
        return True
    if n.endswith("session"):
        return True
    return False


def _direct_code(segs):
    for s in segs:
        m = _CODE.search(s)
        if m:
            return (m.group(1) + m.group(2)).upper()
    return None


def _clean_title(seg):
    return re.sub(r"\s+", " ", seg.strip()).strip(" _-")


def _norm_title(title):
    n = title.lower()
    n = n.replace("gen.", "general").replace("gen ", "general ")
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\bmaths\b", "mathematics", n)
    return re.sub(r"\s+", " ", n).strip()


def _slug(dept_code, title):
    body = re.sub(r"[^A-Za-z0-9]+", "-", title.strip()).strip("-").upper()
    body = "-".join(body.split("-")[:5])      # cap length, keep readable
    return f"{dept_code or 'GEN'}-{body}"[:48]


def _dept_slug(dept_code, level):
    return f"{dept_code}-L{level}" if level else dept_code


def derive_filing(folder_path: str) -> dict:
    """See module docstring. Always returns a dict; course_code is None only for a malformed path
    (no dept and no title) — the single genuinely needs-human filing case."""
    segs = _segments(folder_path)
    if segs and "." in segs[-1]:              # drop the filename
        segs = segs[:-1]

    dept_code = dept_name = None
    dept_idx = None
    for i, s in enumerate(segs):
        hit = _match_dept(s)
        if hit:
            dept_code, dept_name = hit
            dept_idx = i
            break

    level = next((_level(s) for s in segs if _level(s)), None)

    after = segs[dept_idx + 1:] if dept_idx is not None else segs
    title = None
    for s in reversed(after):
        if not _is_structural(s):
            title = _clean_title(s)
            break

    # 1. DIRECT CODE
    code = _direct_code(segs)
    if code:
        return dict(course_code=code, course_title=title, dept=dept_name,
                    confidence="high", source="direct_code")

    # 2. CATALOG / SLUG (title present)
    if title:
        cat = GENERAL_CATALOG.get(_norm_title(title))
        if cat:
            return dict(course_code=cat, course_title=title, dept=dept_name,
                        confidence="high", source="catalog")
        return dict(course_code=_slug(dept_code, title), course_title=title, dept=dept_name,
                    confidence="medium", source="slug")

    # 3. DEPT FALLBACK (no title)
    if dept_code:
        return dict(course_code=_dept_slug(dept_code, level), course_title=None, dept=dept_name,
                    confidence="low", source="dept_fallback")

    # 4. MALFORMED — no dept, no title
    return dict(course_code=None, course_title=None, dept=None,
                confidence="none", source="malformed")
