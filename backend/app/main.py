from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1.counsellor import router as counsellor_router
from backend.app.api.v1.ingest import router as ingest_router
from backend.app.api.v1.keys import router as keys_router
from backend.app.api.v1.predictor import router as predictor_router
from backend.app.api.v1.submissions import router as submissions_router
from backend.app.db.models import Base
from backend.app.db.session import engine

# Initialize Database Schema
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Physics Wallah (PW) In-House GATE Rank, College & PSU Predictor",
    description="Deterministic exam-day evaluation, multi-session normalization, and 3-tier COAP/CCMT/PSU decision engine.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST Routers
app.include_router(predictor_router, prefix="/api/v1")
app.include_router(keys_router, prefix="/api/v1")
app.include_router(submissions_router, prefix="/api/v1")
app.include_router(counsellor_router, prefix="/api/v1")
app.include_router(ingest_router, prefix="/api/v1")

# Static Assets and Web Application
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
@app.get("/student")
def serve_student_portal():
    """
    Serves the Student Exam Portal: personal info, CBT response form,
    TCS Digialm response parser, scorecards, and admission forecasts.
    """
    student_file = STATIC_DIR / "student.html"
    if student_file.exists():
        return FileResponse(str(student_file))
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "status": "healthy",
        "system": "PW GATE Predictor & In-House Ops Engine - Student Portal",
        "version": "1.0.0",
    }


@app.get("/counsellor")
@app.get("/admin")
def serve_counsellor_portal():
    """
    Serves the Counsellor Operations & Admissions Portal:
    KPI triage, candidate lead table, laptop contact details card, and key publisher.
    """
    counsellor_file = STATIC_DIR / "counsellor.html"
    if counsellor_file.exists():
        return FileResponse(str(counsellor_file))
    return {
        "status": "healthy",
        "system": "PW GATE Predictor & In-House Ops Engine - Counsellor Portal",
        "version": "1.0.0",
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "system": "PW GATE Predictor & In-House Ops Engine",
        "version": "1.0.0",
    }
