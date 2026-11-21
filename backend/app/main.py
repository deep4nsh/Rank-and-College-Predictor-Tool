from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.v1.counsellor import router as counsellor_router
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

app.include_router(predictor_router, prefix="/api/v1")
app.include_router(keys_router, prefix="/api/v1")
app.include_router(submissions_router, prefix="/api/v1")
app.include_router(counsellor_router, prefix="/api/v1")


@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "system": "PW GATE Predictor & In-House Ops Engine",
        "version": "1.0.0",
    }
