import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1.counsellor import router as counsellor_router
from backend.app.api.v1.ingest import router as ingest_router
from backend.app.api.v1.keys import router as keys_router
from backend.app.api.v1.predictor import router as predictor_router
from backend.app.api.v1.submissions import router as submissions_router
from backend.app.db.models import Base
from backend.app.db.seed import seed_database
from backend.app.db.session import engine, SessionLocal

# Initialize Database Schema & Auto-Seed Sample Data if empty
Base.metadata.create_all(bind=engine)
try:
    with SessionLocal() as _db:
        seed_database(_db)
except Exception as _e:
    pass

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


@app.middleware("http")
async def handle_head_requests_middleware(request: Request, call_next):
    """
    Ensures full compatibility with uptime monitors (UptimeRobot, BetterUptime)
    that issue HTTP HEAD requests across any endpoint.
    """
    if request.method == "HEAD":
        request.scope["method"] = "GET"
        response = await call_next(request)
        headers = dict(response.headers)
        headers["content-length"] = "0"
        return Response(content=b"", status_code=response.status_code, headers=headers)
    return await call_next(request)

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

PORTAL_MODE = os.getenv("PORTAL_MODE", "both").lower().strip()


NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.api_route("/", methods=["GET", "HEAD"])
def serve_root():
    """
    Dynamically routes root URL '/' based on PORTAL_MODE:
    - 'student': serves Student Exam Portal
    - 'counsellor': serves Counsellor Operations Station
    - 'both': defaults to Student Portal with counsellor reachable at /counsellor
    """
    if PORTAL_MODE == "counsellor":
        return serve_counsellor_portal()
    return serve_student_portal()


@app.api_route("/student", methods=["GET", "HEAD"])
def serve_student_portal():
    """
    Serves the Student Exam Portal: personal info, CBT response form,
    TCS Digialm response parser, scorecards, and admission forecasts.
    """
    if PORTAL_MODE == "counsellor":
        raise HTTPException(
            status_code=404,
            detail="Student portal is not enabled on this service. Please visit the Student Portal URL.",
        )
    student_file = STATIC_DIR / "student.html"
    if student_file.exists():
        return FileResponse(str(student_file), headers=NO_CACHE_HEADERS)
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file), headers=NO_CACHE_HEADERS)
    return {
        "status": "healthy",
        "system": "PW GATE Predictor & In-House Ops Engine - Student Portal",
        "version": "1.0.0",
    }


@app.api_route("/counsellor", methods=["GET", "HEAD"])
@app.api_route("/admin", methods=["GET", "HEAD"])
def serve_counsellor_portal():
    """
    Serves the Counsellor Operations & Admissions Portal:
    KPI triage, candidate lead table, laptop contact details card, and key publisher.
    """
    if PORTAL_MODE == "student":
        raise HTTPException(
            status_code=404,
            detail="Counsellor station is not enabled on this service. Please visit the Counsellor Station URL.",
        )
    counsellor_file = STATIC_DIR / "counsellor.html"
    if counsellor_file.exists():
        return FileResponse(str(counsellor_file), headers=NO_CACHE_HEADERS)
    return {
        "status": "healthy",
        "system": "PW GATE Predictor & In-House Ops Engine - Counsellor Portal",
        "version": "1.0.0",
    }


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/api/health", methods=["GET", "HEAD"])
@app.api_route("/api/v1/health", methods=["GET", "HEAD"])
def health_check():
    return {
        "status": "healthy",
        "system": "PW GATE Predictor & In-House Ops Engine",
        "version": "1.0.0",
    }
