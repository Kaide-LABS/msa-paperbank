from app.course_filing import derive_filing

ENG = "root/SST (School of Science and Technology)/Engineering/"
SMSS = "root/SMSS (School of Management and Social Sciences)/"


def test_direct_code_wins():
    f = derive_filing(ENG + "Electrical Engineering/300 level/1st Semester/2023-2024/EEE321/Scanned.pdf")
    assert f["course_code"] == "EEE321"
    assert f["source"] == "direct_code" and f["confidence"] == "high"

def test_catalog_known_title_maps_to_official_code():
    f = derive_filing(SMSS + "Business Administration/200 level/1st Semester/2022-2023/Communication in English/x.jpg")
    assert f["course_code"] == "GST111" and f["source"] == "catalog"
    g = derive_filing(ENG + "100 Level/1st Semester/EMME/2024-2025/Gen. Chemistry 1/Scanned.pdf")
    assert g["course_code"] == "CHM101" and g["source"] == "catalog"

def test_unknown_title_gets_a_filable_slug_not_a_human():
    f = derive_filing(SMSS + "Finance/100 level/1st Semester /2024-2025/Introduction to Finance/Exam.jpg")
    assert f["source"] == "slug" and f["confidence"] == "medium"
    assert f["course_code"] and f["dept"] == "Finance" and f["course_title"] == "Introduction to Finance"
    # slug is STABLE/deterministic across other instances of the same course (groups consistently)
    other = derive_filing(SMSS + "Finance/200 level/2nd Semester/2023-2024/Introduction to Finance/y.jpg")
    assert other["course_code"] == f["course_code"]
    # and it never fabricates an official-looking code
    assert not f["course_code"][:3].isalpha() or "-" in f["course_code"]

def test_no_title_dept_fallback_is_still_filable():
    f = derive_filing(SMSS + "Finance/100 level/1st Semester /20230516_233558.jpg")
    assert f["source"] == "dept_fallback" and f["course_code"] and f["dept"] == "Finance"
    assert f["course_title"] is None

def test_malformed_path_is_the_only_unfilable_case():
    f = derive_filing("random_photo.jpg")     # no folders -> no dept, no title
    assert f["course_code"] is None and f["dept"] is None and f["source"] == "malformed"
