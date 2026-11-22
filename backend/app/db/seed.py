"""
Sample Data Seeder for Physics Wallah GATE Predictor & Counsellor Operations.
Populates realistic sample students, evaluations across all GATE branches,
lead priorities (SUPER_TOPPER, PSU_AND_TOP_IIT, NIT_PROSPECT, NURTURE_REPEATER),
high-negative marks candidates, and chronological counsellor call logs.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from backend.app.db.models import (
    CounsellorCallLogModel,
    EvaluationResultModel,
    PaperModel,
    StudentSubmissionModel,
)


SAMPLE_STUDENTS = [
    {
        "name": "Rohan Sharma",
        "phone": "9876543210",
        "email": "rohan.sharma@example.com",
        "category": "GEN",
        "paper": "CS",
        "raw": 88.33,
        "neg": 1.67,
        "gate_score": 945,
        "air": 12,
        "air_min": 10,
        "air_max": 15,
        "priority": "SUPER_TOPPER",
        "disp": "COAP_COUNSELLING_BOOKED",
        "btech": 88.5,
        "age": 22,
        "ncl": True,
        "batch": "PW Shreshth CS 2025",
        "call_logs": [
            ("Pooja Sharma", "CONNECTED_FOLLOW_UP", "Candidate scored very high. Discussed IISc CSA vs IIT Bombay CSE.", -2),
            ("Pooja Sharma", "COAP_COUNSELLING_BOOKED", "Booked 1-on-1 COAP strategy session with Senior Faculty.", -1),
        ],
    },
    {
        "name": "Ananya Verma",
        "phone": "9876543211",
        "email": "ananya.v@example.com",
        "category": "OBC",
        "paper": "DA",
        "raw": 84.67,
        "neg": 2.33,
        "gate_score": 915,
        "air": 28,
        "air_min": 24,
        "air_max": 32,
        "priority": "SUPER_TOPPER",
        "disp": "PSU_GDPI_BOOKED",
        "btech": 84.0,
        "age": 23,
        "ncl": True,
        "batch": "PW Data Science & AI Elite",
        "call_logs": [
            ("Aditya Roy", "PSU_GDPI_BOOKED", "Interested in ONGC Data Scientist post. Scheduled GD/PI interview prep.", -3),
        ],
    },
    {
        "name": "Tanmay Sen",
        "phone": "9876543224",
        "email": "tanmay.sen@example.com",
        "category": "GEN",
        "paper": "CE",
        "raw": 79.33,
        "neg": 2.00,
        "gate_score": 840,
        "air": 92,
        "air_min": 85,
        "air_max": 105,
        "priority": "SUPER_TOPPER",
        "disp": "COAP_COUNSELLING_BOOKED",
        "btech": 82.0,
        "age": 22,
        "ncl": True,
        "batch": "PW Parakram CE",
        "call_logs": [
            ("Pooja Sharma", "COAP_COUNSELLING_BOOKED", "Top 100 rank confirmed. Advised choice order for IIT Delhi/Roorkee.", -2),
        ],
    },
    {
        "name": "Siddharth Iyer",
        "phone": "9876543212",
        "email": "siddharth.i@example.com",
        "category": "GEN",
        "paper": "ME",
        "raw": 75.00,
        "neg": 3.00,
        "gate_score": 795,
        "air": 215,
        "air_min": 190,
        "air_max": 240,
        "priority": "PSU_AND_TOP_IIT",
        "disp": "INTERESTED_IN_BATCH",
        "btech": 78.0,
        "age": 23,
        "ncl": True,
        "batch": "PW Mechanical Dropper",
        "call_logs": [
            ("Ramesh Guha", "INTERESTED_IN_BATCH", "Targeting IOCL/BHEL. Enquired about PSU Interview prep course.", -4),
        ],
    },
    {
        "name": "Priya Patel",
        "phone": "9876543213",
        "email": "priya.patel@example.com",
        "category": "EWS",
        "paper": "CE",
        "raw": 73.33,
        "neg": 4.67,
        "gate_score": 775,
        "air": 280,
        "air_min": 250,
        "air_max": 310,
        "priority": "PSU_AND_TOP_IIT",
        "disp": "CONNECTED_FOLLOW_UP",
        "btech": 75.0,
        "age": 22,
        "ncl": True,
        "batch": "PW Parakram CE",
        "call_logs": [
            ("Ramesh Guha", "CONNECTED_FOLLOW_UP", "EWS category advantage discussed. Follow-up after mock round.", -1),
        ],
    },
    {
        "name": "Vikram Singh",
        "phone": "9876543214",
        "email": "vikram.s@example.com",
        "category": "GEN",
        "paper": "EE",
        "raw": 71.00,
        "neg": 4.00,
        "gate_score": 750,
        "air": 340,
        "air_min": 310,
        "air_max": 380,
        "priority": "PSU_AND_TOP_IIT",
        "disp": "INTERESTED_IN_BATCH",
        "btech": 76.5,
        "age": 23,
        "ncl": True,
        "batch": "PW Electrical Pro",
        "call_logs": [
            ("Aditya Roy", "INTERESTED_IN_BATCH", "PowerGrid executive trainee interest. Sent brochure.", -5),
        ],
    },
    {
        "name": "Sneha Kulkarni",
        "phone": "9876543215",
        "email": "sneha.k@example.com",
        "category": "OBC",
        "paper": "EC",
        "raw": 68.67,
        "neg": 5.33,
        "gate_score": 725,
        "air": 450,
        "air_min": 410,
        "air_max": 490,
        "priority": "PSU_AND_TOP_IIT",
        "disp": "PENDING",
        "btech": 73.0,
        "age": 22,
        "ncl": True,
        "batch": "PW ECE Batch",
        "call_logs": [],
    },
    # High Negative Marks Candidates (>8 marks lost)
    {
        "name": "Amit Kumar",
        "phone": "9876543216",
        "email": "amit.k@example.com",
        "category": "GEN",
        "paper": "CS",
        "raw": 53.00,
        "neg": 11.33,
        "gate_score": 605,
        "air": 1650,
        "air_min": 1500,
        "air_max": 1800,
        "priority": "NIT_PROSPECT",
        "disp": "INTERESTED_IN_BATCH",
        "btech": 71.0,
        "age": 23,
        "ncl": True,
        "batch": None,
        "call_logs": [
            ("Pooja Sharma", "INTERESTED_IN_BATCH", "Lost 11.33 marks to negative marking! High potential for top 100 with accuracy training. Strongly interested in PW Rank Improvement batch.", -2),
        ],
    },
    {
        "name": "Megha Reddy",
        "phone": "9876543217",
        "email": "megha.r@example.com",
        "category": "SC",
        "paper": "DA",
        "raw": 48.00,
        "neg": 9.67,
        "gate_score": 550,
        "air": 2400,
        "air_min": 2200,
        "air_max": 2600,
        "priority": "NIT_PROSPECT",
        "disp": "CONNECTED_FOLLOW_UP",
        "btech": 69.5,
        "age": 22,
        "ncl": True,
        "batch": "PW Data Science Pro",
        "call_logs": [
            ("Aditya Roy", "CONNECTED_FOLLOW_UP", "Exam stress caused 7 negative MCQ errors. SC category offers IIT MTech chance. Follow up tomorrow.", -1),
        ],
    },
    {
        "name": "Rahul Nair",
        "phone": "9876543218",
        "email": "rahul.n@example.com",
        "category": "GEN",
        "paper": "ME",
        "raw": 57.33,
        "neg": 8.67,
        "gate_score": 635,
        "air": 1300,
        "air_min": 1200,
        "air_max": 1450,
        "priority": "NIT_PROSPECT",
        "disp": "PENDING",
        "btech": 72.0,
        "age": 23,
        "ncl": True,
        "batch": None,
        "call_logs": [],
    },
    # NIT Prospects & Nurture Repeater Candidates
    {
        "name": "Kavita Choudhary",
        "phone": "9876543223",
        "email": "kavita.c@example.com",
        "category": "EWS",
        "paper": "DA",
        "raw": 63.00,
        "neg": 3.67,
        "gate_score": 695,
        "air": 780,
        "air_min": 720,
        "air_max": 850,
        "priority": "NIT_PROSPECT",
        "disp": "COAP_COUNSELLING_BOOKED",
        "btech": 81.0,
        "age": 22,
        "ncl": True,
        "batch": "PW DA Elite",
        "call_logs": [
            ("Aditya Roy", "COAP_COUNSELLING_BOOKED", "Booked COAP counselling for Gen-2 IITs (IIT Jodhpur, IIT Ropar AI).", -3),
        ],
    },
    {
        "name": "Pooja Das",
        "phone": "9876543219",
        "email": "pooja.das@example.com",
        "category": "ST",
        "paper": "CE",
        "raw": 39.00,
        "neg": 4.00,
        "gate_score": 505,
        "air": 3400,
        "air_min": 3100,
        "air_max": 3700,
        "priority": "NIT_PROSPECT",
        "disp": "INTERESTED_IN_BATCH",
        "btech": 68.0,
        "age": 24,
        "ncl": True,
        "batch": None,
        "call_logs": [
            ("Ramesh Guha", "INTERESTED_IN_BATCH", "ST category eligible for NIT Trichy/Surathkal. Offered CCMT admission guidance package.", -4),
        ],
    },
    {
        "name": "Kartik Jain",
        "phone": "9876543220",
        "email": "kartik.j@example.com",
        "category": "GEN",
        "paper": "EE",
        "raw": 42.67,
        "neg": 6.33,
        "gate_score": 490,
        "air": 3900,
        "air_min": 3600,
        "air_max": 4300,
        "priority": "NIT_PROSPECT",
        "disp": "PENDING",
        "btech": 70.0,
        "age": 23,
        "ncl": True,
        "batch": None,
        "call_logs": [],
    },
    {
        "name": "Deepa Sundaram",
        "phone": "9876543221",
        "email": "deepa.s@example.com",
        "category": "OBC",
        "paper": "EC",
        "raw": 33.33,
        "neg": 5.67,
        "gate_score": 410,
        "air": 7200,
        "air_min": 6800,
        "air_max": 7600,
        "priority": "NURTURE_REPEATER",
        "disp": "INTERESTED_IN_BATCH",
        "btech": 66.0,
        "age": 22,
        "ncl": True,
        "batch": None,
        "call_logs": [
            ("Pooja Sharma", "INTERESTED_IN_BATCH", "Final year college student. Looking to take a drop year for GATE 2026. Offered 25% early bird discount for PW Shreshth batch.", -2),
        ],
    },
    {
        "name": "Harish Rawat",
        "phone": "9876543222",
        "email": "harish.r@example.com",
        "category": "GEN",
        "paper": "CS",
        "raw": 29.00,
        "neg": 7.00,
        "gate_score": 365,
        "air": 9100,
        "air_min": 8500,
        "air_max": 9800,
        "priority": "NURTURE_REPEATER",
        "disp": "CONNECTED_FOLLOW_UP",
        "btech": 64.5,
        "age": 23,
        "ncl": True,
        "batch": None,
        "call_logs": [
            ("Pooja Sharma", "CONNECTED_FOLLOW_UP", "Needs foundational syllabus coverage in Operating Systems & Algorithms. Shared demo lecture link.", -1),
        ],
    },
]


def seed_database(db: Session, force: bool = False) -> int:
    """
    Seeds database with initial papers, questions, and realistic student leads.
    Returns the count of seeded students.
    """
    # 1. Provision Papers
    papers = ["CS", "DA", "ME", "CE", "EE", "EC"]
    for p_code in papers:
        existing = db.query(PaperModel).filter(PaperModel.paper_code == p_code).first()
        if not existing:
            db.add(PaperModel(paper_code=p_code, year=2025, is_multi_session=(p_code in ["CS", "CE", "ME"])))
    db.commit()

    # Check if student data already exists
    current_count = db.query(StudentSubmissionModel).count()
    if current_count > 0 and not force:
        return current_count

    now_utc = datetime.now(timezone.utc)
    seeded = 0

    for s in SAMPLE_STUDENTS:
        # Check if student phone already exists
        existing_sub = db.query(StudentSubmissionModel).filter(StudentSubmissionModel.student_phone == s["phone"]).first()
        if existing_sub:
            continue

        submission = StudentSubmissionModel(
            student_phone=s["phone"],
            student_name=s["name"],
            student_email=s["email"],
            student_category=s["category"],
            btech_percentage=s["btech"],
            candidate_age=s["age"],
            has_valid_ncl=s["ncl"],
            pw_batch_id=s["batch"],
            paper_code=s["paper"],
            session_id=1,
            is_active=True,
            call_disposition=s["disp"],
            last_contacted_at=now_utc - timedelta(days=1) if s["call_logs"] else None,
            submitted_at=now_utc - timedelta(days=2),
        )
        db.add(submission)
        db.flush()

        apt_score = round(min(15.0, s["raw"] * 0.18), 2)
        core_score = round(s["raw"] - apt_score, 2)

        evaluation = EvaluationResultModel(
            submission_id=submission.submission_id,
            key_id=None,
            raw_score_total=s["raw"],
            raw_score_aptitude=apt_score,
            raw_score_core=core_score,
            marks_lost_to_negatives=s["neg"],
            correct_count=int(s["raw"] * 0.7),
            incorrect_count=int(s["neg"] * 1.5),
            unattempted_count=max(0, 65 - int(s["raw"] * 0.7) - int(s["neg"] * 1.5)),
            normalized_marks=s["raw"],
            gate_score=s["gate_score"],
            predicted_air=s["air"],
            air_range_min=s["air_min"],
            air_range_max=s["air_max"],
            lead_classification=s["priority"],
            evaluated_at=now_utc - timedelta(days=2),
        )
        db.add(evaluation)

        # Seed call logs
        for c_name, c_disp, c_notes, days_ago in s["call_logs"]:
            call_log = CounsellorCallLogModel(
                submission_id=submission.submission_id,
                student_phone=s["phone"],
                counsellor_name=c_name,
                call_disposition=c_disp,
                notes=c_notes,
                follow_up_date=(now_utc + timedelta(days=2)).strftime("%Y-%m-%d"),
                logged_at=now_utc + timedelta(days=days_ago),
            )
            db.add(call_log)

        seeded += 1

    db.commit()
    return seeded
