from sqlalchemy.orm import sessionmaker
from backend.app.db.models import Base
from backend.app.db.session import engine
from backend.app.services.bulk_importer import parse_csv_or_tsv_content, process_bulk_import

SessionTest = sessionmaker(bind=engine)


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_parse_csv_and_tsv_formats():
    csv_str = "student_phone,student_name,paper_code\n9876543210,Ramesh Kumar,CS\n"
    res_csv = parse_csv_or_tsv_content(csv_str)
    assert len(res_csv) == 1
    assert res_csv[0]["student_phone"] == "9876543210"
    assert res_csv[0]["student_name"] == "Ramesh Kumar"

    tsv_str = "student_phone\tstudent_name\tpaper_code\n9876543211\tSuresh Raina\tME\n"
    res_tsv = parse_csv_or_tsv_content(tsv_str)
    assert len(res_tsv) == 1
    assert res_tsv[0]["student_phone"] == "9876543211"
    assert res_tsv[0]["student_name"] == "Suresh Raina"


def test_bulk_import_direct_score_mode():
    db = SessionTest()
    try:
        csv_content = """student_phone,student_name,student_category,paper_code,session_id,btech_percentage,candidate_age,raw_score
9898989801,Kavita Krishnan,GEN,CS,1,78.5,23,76.5
9898989802,Ankit Verma,OBC_NCL,CS,1,68.0,24,45.0
9898989803,Troll BadPhone,GEN,CS,1,60.0,25,30.0
"""
        # Change 3rd row to invalid phone
        csv_with_err = csv_content.replace("9898989803", "123")  # invalid phone

        result = process_bulk_import(csv_with_err, db)
        assert result.total_rows == 3
        assert result.successful_count == 2
        assert result.failed_count == 1
        assert len(result.errors) == 1
        assert result.errors[0]["student_phone"] == "123"

        # Check that high scorer got proper lead category
        assert "9898989801" in result.successful_phones
        assert result.lead_distribution.get("SUPER_TOPPER", 0) + result.lead_distribution.get("PSU_AND_TOP_IIT", 0) >= 1
    finally:
        db.close()
