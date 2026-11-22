import base64
import hashlib
import hmac
import os
import time
from typing import Optional
from fastapi import Header, HTTPException, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Configurable Passcode and Secret Key
COUNSELLOR_PASSWORD = os.getenv("COUNSELLOR_PASSWORD", "Councellor@123")
AUTH_SECRET = os.getenv("AUTH_SECRET", "pw-gate-counsellor-secret-key-2025")
TOKEN_EXPIRY_SECONDS = 86400 * 7  # 7 days

security_bearer = HTTPBearer(auto_error=False)


def generate_session_token(counsellor_name: str = "PW Counsellor") -> str:
    """
    Generates a tamper-proof HMAC-SHA256 session token with timestamp.
    """
    ts = int(time.time())
    payload = f"{counsellor_name}:{ts}"
    signature = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    raw_token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw_token.encode("utf-8")).decode("utf-8")


def verify_token(token: str) -> bool:
    """
    Verifies that the provided token was signed with AUTH_SECRET and has not expired.
    Also accepts direct raw passcode 'Councellor@123' for maximum flexibility.
    """
    if not token:
        return False

    # Allow direct passcode comparison
    if token == COUNSELLOR_PASSWORD:
        return True

    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        parts = decoded.split(":")
        if len(parts) != 3:
            return False

        counsellor_name, ts_str, signature = parts
        ts = int(ts_str)

        # Check expiry
        if time.time() - ts > TOKEN_EXPIRY_SECONDS:
            return False

        # Verify HMAC signature
        expected_payload = f"{counsellor_name}:{ts}"
        expected_sig = hmac.new(
            AUTH_SECRET.encode("utf-8"),
            expected_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected_sig)
    except Exception:
        return False


def verify_counsellor_access(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    x_counsellor_passcode: Optional[str] = Header(None, alias="X-Counsellor-Passcode"),
    x_counsellor_token: Optional[str] = Header(None, alias="X-Counsellor-Token"),
    token: Optional[str] = Query(None),
    passcode: Optional[str] = Query(None),
) -> str:
    """
    FastAPI Dependency to guard Counsellor and Faculty Admin endpoints.
    Accepts:
    1. Authorization: Bearer <token_or_passcode>
    2. X-Counsellor-Passcode or X-Counsellor-Token header
    3. Query parameter ?token= or ?passcode= (for PDF and CSV download links)
    4. Cookie 'counsellor_token'
    """
    # 1. Check Bearer token
    if bearer and bearer.credentials:
        if verify_token(bearer.credentials):
            return "authenticated"

    # 2. Check Custom Headers
    for candidate in [x_counsellor_passcode, x_counsellor_token]:
        if candidate and verify_token(candidate):
            return "authenticated"

    # 3. Check Query Parameters (supports browser direct downloads)
    for candidate in [token, passcode]:
        if candidate and verify_token(candidate):
            return "authenticated"

    # 4. Check Cookie
    cookie_token = request.cookies.get("counsellor_token")
    if cookie_token and verify_token(cookie_token):
        return "authenticated"

    # If all checks fail, raise 401 Unauthorized
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Counsellor authentication required. Invalid passcode or expired session.",
        headers={"WWW-Authenticate": "Bearer"},
    )
