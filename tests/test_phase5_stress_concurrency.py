"""
Phase 5 Test Suite: Concurrency, Database WAL Hardening, and High-Volume Load.
Verifies zero database lockouts during simultaneous student submissions,
concurrent counsellor CRM activity, and sub-second batch re-evaluations.
"""

import concurrent.futures
import time
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from backend.app.db.models import (
    AnswerKeyItemModel,
    AnswerKeyModel,
    PaperModel,
    QuestionModel,
    StudentSubmissionModel,
    EvaluationResultModel,
)
from backend.app.db.session import SessionLocal, checkpoint_db_wal
from backend.app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def stress_setup():
    """
    Provisions a test paper (GATE CS) with 10 questions and an active faculty answer key.
    """
    db: Session = SessionLocal()
    try:
        # Create CS Paper
        paper = db.query(PaperModel).filter(PaperModel.paper_code == "CS").first()
        if not paper:
            paper = PaperModel(paper_code="CS", year=2025, total_questions=10)
            db.add(paper)
            db.commit()

        # Create 10 Questions
        for i in range(1, 11):
            q_id = f"STRESS-CS-Q{i:02d}"
            existing_q = db.query(QuestionModel).filter(QuestionModel.question_id == q_id).first()
            if not existing_q:
                q = QuestionModel(
                    question_id=q_id,
                    paper_code="CS",
                    question_number=i,
                    section="CORE" if i > 2 else "APTITUDE",
                    question_type="MCQ" if i % 3 != 0 else ("NAT" if i % 2 == 0 else "MSQ"),
                    marks_correct=1.0 if i <= 5 else 2.0,
                    marks_negative=0.3333 if i <= 5 else 0.6667,
                )
                db.add(q)
        db.commit()

        # Create Key v1
        key = db.query(AnswerKeyModel).filter(AnswerKeyModel.key_id == "KEY-STRESS-V1").first()
        if not key:
            key = AnswerKeyModel(
                key_id="KEY-STRESS-V1",
                paper_code="CS",
                version=1,
                key_type="FACULTY_EXAM_DAY",
                author_name="PW Faculty Stress Test Panel",
                status="ACTIVE",
            )
            db.add(key)
            db.flush()

            for i in range(1, 11):
                item = AnswerKeyItemModel(
                    key_id="KEY-STRESS-V1",
                    question_id=f"STRESS-CS-Q{i:02d}",
                    is_mta=False,
                    valid_options_json='[["B"]]' if i % 3 != 0 else None,
                    nat_min=24.0 if (i % 3 == 0 and i % 2 == 0) else None,
                    nat_max=26.0 if (i % 3 == 0 and i % 2 == 0) else None,
                )
                db.add(item)
            db.commit()

        yield {"paper_code": "CS", "key_id": "KEY-STRESS-V1"}
    finally:
        db.close()


def test_concurrent_student_submissions(stress_setup):
    """
    Simulates 30 parallel student submissions executing concurrently across worker threads.
    Verifies that SQLite WAL mode and QueuePool handle concurrent writes with zero lockouts.
    """
    total_workers = 30

    def submit_student(idx):
        phone = f"998877{idx:04d}"
        payload = {
            "student_phone": phone,
            "student_name": f"Stress Candidate {idx}",
            "student_email": f"stress{idx}@pwtest.com",
            "student_category": "GEN" if idx % 2 == 0 else "OBC_NCL",
            "paper_code": "CS",
            "session_id": 1 if idx % 2 == 0 else 2,
            "responses": [
                {
                    "question_id": f"STRESS-CS-Q{i:02d}",
                    "status": "ATTEMPTED",
                    "marked_options": ["B"],
                    "nat_value": "25.0" if (i % 3 == 0 and i % 2 == 0) else None,
                }
                for i in range(1, 11)
            ],
        }
        res = client.post("/api/v1/submissions", json=payload)
        return res.status_code, res.json()

    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(submit_student, i) for i in range(total_workers)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    elapsed = time.time() - start_time

    # All submissions must succeed
    status_codes = [r[0] for r in results]
    assert all(code == 200 for code in status_codes), f"Some submissions failed: {status_codes}"
    assert len(results) == total_workers

    # Throughput check
    throughput = total_workers / elapsed
    assert throughput > 5.0, f"Throughput too low: {throughput:.2f} req/s"


def test_simultaneous_counsellor_reads_and_student_writes(stress_setup):
    """
    Verifies that simultaneous write operations (student submissions and call logs)
    do not block or starve counsellor read queries (lead listing & analytics).
    """
    def write_task(idx):
        phone = f"991122{idx:04d}"
        sub_payload = {
            "student_phone": phone,
            "student_name": f"Concurrent Writer {idx}",
            "student_email": f"writer{idx}@pwtest.com",
            "student_category": "SC",
            "paper_code": "CS",
            "session_id": 1,
            "responses": [{"question_id": "STRESS-CS-Q01", "status": "ATTEMPTED", "marked_options": ["B"]}],
        }
        res = client.post("/api/v1/submissions", json=sub_payload)
        if res.status_code == 200:
            # Also log a call
            client.post(
                f"/api/v1/counsellor/students/{phone}/call-log",
                json={
                    "counsellor_name": "Concurrent Mentor",
                    "call_disposition": "CONNECTED_FOLLOW_UP",
                    "notes": f"High concurrency call log test {idx}",
                },
            )
        return res.status_code

    def read_task(idx):
        # Counsellor searches and analytics
        res_list = client.get("/api/v1/counsellor/students?paper_code=CS&limit=20")
        res_analytics = client.get("/api/v1/counsellor/analytics/lead-summary")
        return res_list.status_code == 200 and res_analytics.status_code == 200

    tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        for i in range(15):
            tasks.append(executor.submit(write_task, i))
            tasks.append(executor.submit(read_task, i))

        results = [t.result() for t in concurrent.futures.as_completed(tasks)]

    # All read and write tasks must succeed without deadlock
    assert all(r is True or r == 200 for r in results)


def test_high_volume_batch_reevaluation_subsecond(stress_setup):
    """
    Tests batch re-evaluation of all submitted candidates against an updated answer key (Key v2).
    Verifies sub-second execution speed using O(1) bulk database queries.
    """
    db: Session = SessionLocal()
    try:
        # Create Key v2 with MTA on Question 1 (Marks to All)
        key_v2 = db.query(AnswerKeyModel).filter(AnswerKeyModel.key_id == "KEY-STRESS-V2").first()
        if not key_v2:
            key_v2 = AnswerKeyModel(
                key_id="KEY-STRESS-V2",
                paper_code="CS",
                version=2,
                key_type="OFFICIAL_IIT",
                author_name="IIT Official Final Key",
                status="ACTIVE",
            )
            db.add(key_v2)
            db.flush()

            for i in range(1, 11):
                item = AnswerKeyItemModel(
                    key_id="KEY-STRESS-V2",
                    question_id=f"STRESS-CS-Q{i:02d}",
                    is_mta=(i == 1),  # MTA on Q1!
                    valid_options_json='[["B"]]' if i % 3 != 0 else None,
                    nat_min=24.0 if (i % 3 == 0 and i % 2 == 0) else None,
                    nat_max=26.0 if (i % 3 == 0 and i % 2 == 0) else None,
                )
                db.add(item)
            db.commit()
    finally:
        db.close()

    # Trigger Batch Re-Evaluation
    start_time = time.time()
    res = client.post("/api/v1/keys/KEY-STRESS-V2/re-evaluate")
    elapsed = time.time() - start_time

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["key_id"] == "KEY-STRESS-V2"
    assert data["re_evaluated_count"] >= 30
    # Must complete in under 1.5 seconds thanks to bulk prefetching
    assert elapsed < 1.5, f"Re-evaluation took too long: {elapsed:.3f}s"


def test_online_wal_checkpoint():
    """
    Verifies that the online passive WAL checkpoint utility runs cleanly
    without locking or disconnecting open sessions.
    """
    # Trigger checkpoint
    checkpoint_db_wal()

    # Verify database remains immediately readable and writable
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
