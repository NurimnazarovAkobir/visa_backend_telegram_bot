import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Literal

from fastapi import Body, Cookie, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from database import (
    get_lead,
    init_db,
    list_leads,
    update_payment_method,
    update_payment_status,
)


app = FastAPI(
    title="Visa Leads Admin API",
    version="1.2.0",
    description=(
        "Admin-only API for Telegram bot leads. "
        "Users submit data only through the Telegram bot; admin reads and manages it here."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer(auto_error=False)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str = Field(validation_alias="email")
    password: str


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    telegram_chat_id: int
    language: str
    nationality: str
    full_name: str
    birth_date: str
    russian_level: int
    agriculture_experience: str
    phone_primary: str
    phone_secondary: str | None
    email: str
    passport_file_id: str
    passport_kind: str
    payment_status: str
    payment_method: str | None
    receipt_file_id: str | None
    receipt_kind: str | None
    passport_open_url: str
    receipt_open_url: str | None
    created_at: str


class PaymentUpdateRequest(BaseModel):
    payment_method: Literal["payme", "click", "uzum", "paynet", "humo_uzcard", "visa_mastercard"]


class PaymentStatusUpdateRequest(BaseModel):
    payment_status: Literal["pending", "paid", "error"]


class MessageResponse(BaseModel):
    status: str


class ReceiptResponse(BaseModel):
    lead_id: int
    payment_status: str
    payment_method: str | None
    receipt_file_id: str
    receipt_kind: str | None
    receipt_open_url: str


class LeadStatsResponse(BaseModel):
    total: int
    pending_payment: int
    paid_payment: int
    error_payment: int


def load_env() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        os.environ.setdefault(key.strip(), value.strip())


def get_admin_email() -> str:
    email = os.getenv("ADMIN_EMAIL")
    if not email:
        raise HTTPException(status_code=500, detail="ADMIN_EMAIL is not configured")
    return email


def get_admin_password() -> str:
    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD is not configured")
    return password


def get_auth_secret() -> str:
    secret = os.getenv("AUTH_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="AUTH_SECRET is not configured")
    return secret


def get_bot_token() -> str:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not configured")
    return token


def get_telegram_file_path(file_id: str) -> str:
    bot_token = get_bot_token()
    encoded_file_id = urllib.parse.quote(file_id, safe="")
    request_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={encoded_file_id}"
    try:
        with urllib.request.urlopen(request_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to reach Telegram API") from exc

    if not payload.get("ok"):
        description = payload.get("description", "Telegram file lookup failed")
        raise HTTPException(status_code=404, detail=description)

    result = payload.get("result") or {}
    file_path = result.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="Telegram file path not found")
    return file_path


def send_telegram_message(chat_id: int, text: str) -> None:
    request_url = f"https://api.telegram.org/bot{get_bot_token()}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": str(chat_id),
            "text": text,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        request_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to send Telegram message") from exc

    if not response_payload.get("ok"):
        description = response_payload.get("description", "Telegram sendMessage failed")
        raise HTTPException(status_code=502, detail=description)


def build_admin_file_url(request: Request, file_id: str | None) -> str | None:
    if not file_id:
        return None
    return str(request.url_for("open_telegram_file", file_id=file_id))


def serialize_lead(request: Request, lead: dict) -> LeadResponse:
    payload = {
        **lead,
        "passport_open_url": build_admin_file_url(request, lead["passport_file_id"]),
        "receipt_open_url": build_admin_file_url(request, lead.get("receipt_file_id")),
    }
    return LeadResponse.model_validate(payload)


def serialize_receipt(request: Request, lead: dict) -> ReceiptResponse:
    receipt_file_id = lead.get("receipt_file_id")
    if not receipt_file_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    payload = {
        "lead_id": lead["id"],
        "payment_status": lead["payment_status"],
        "payment_method": lead.get("payment_method"),
        "receipt_file_id": receipt_file_id,
        "receipt_kind": lead.get("receipt_kind"),
        "receipt_open_url": build_admin_file_url(request, receipt_file_id),
    }
    return ReceiptResponse.model_validate(payload)


def create_login_response(response: Response, username: str, password: str) -> TokenResponse:
    if username != get_admin_email() or password != get_admin_password():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    access_token = create_access_token(username)
    response.set_cookie(
        key="admin_access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
    )
    return TokenResponse(access_token=access_token)


def encode_segment(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def decode_segment(segment: str) -> dict:
    padding = "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode(segment + padding)
    return json.loads(raw.decode("utf-8"))


def sign_value(value: str, secret: str) -> str:
    signature = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")


def create_access_token(subject: str, expires_in: int = 60 * 60 * 12) -> str:
    payload = {
        "sub": subject,
        "exp": int(time.time()) + expires_in,
    }
    encoded_payload = encode_segment(payload)
    signature = sign_value(encoded_payload, get_auth_secret())
    return f"{encoded_payload}.{signature}"


def verify_access_token(token: str) -> dict:
    try:
        encoded_payload, signature = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    expected_signature = sign_value(encoded_payload, get_auth_secret())
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid access token")

    payload = decode_segment(encoded_payload)
    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Access token expired")
    return payload


def extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    admin_access_token: str | None,
    query_token: str | None,
) -> str:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    if admin_access_token:
        return admin_access_token
    if query_token:
        return query_token
    raise HTTPException(status_code=401, detail="Not authenticated")


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    admin_access_token: str | None = Cookie(default=None),
    token: str | None = Query(default=None),
) -> str:
    payload = verify_access_token(extract_token(credentials, admin_access_token, token))
    if payload.get("sub") != get_admin_email():
        raise HTTPException(status_code=401, detail="Invalid admin user")
    return payload["sub"]


@app.on_event("startup")
def on_startup() -> None:
    load_env()
    init_db()


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["auth"],
    summary="Admin login",
)
async def auth_login(request: Request, response: Response) -> TokenResponse:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload = LoginRequest.model_validate(await request.json())
        return create_login_response(response, payload.username, payload.password)

    form_data = await request.form()
    username = form_data.get("username") or form_data.get("email")
    password = form_data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        raise HTTPException(status_code=422, detail="username/email and password are required")
    return create_login_response(response, username, password)


@app.post(
    "/login",
    response_model=TokenResponse,
    tags=["auth"],
    summary="Admin login (JSON)",
)
def login_alias(response: Response, payload: LoginRequest = Body(...)) -> TokenResponse:
    return create_login_response(response, payload.username, payload.password)


@app.post(
    "/auth/logout",
    response_model=MessageResponse,
    tags=["auth"],
    summary="Admin logout",
)
def auth_logout(response: Response) -> MessageResponse:
    response.delete_cookie("admin_access_token")
    return MessageResponse(status="logged_out")


@app.post(
    "/logout",
    response_model=MessageResponse,
    tags=["auth"],
    summary="Admin logout alias",
)
def logout_alias(response: Response) -> MessageResponse:
    return auth_logout(response)


@app.get("/health", response_model=MessageResponse, tags=["system"])
def health() -> MessageResponse:
    return MessageResponse(status="ok")


@app.get(
    "/files/{file_id}",
    dependencies=[Depends(require_admin)],
    tags=["admin"],
    summary="Open stored Telegram file by file_id",
)
def open_telegram_file(file_id: str) -> RedirectResponse:
    file_path = get_telegram_file_path(file_id)
    file_url = f"https://api.telegram.org/file/bot{get_bot_token()}/{file_path}"
    return RedirectResponse(url=file_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get(
    "/admin/leads/{lead_id}/receipt-info",
    response_model=ReceiptResponse,
    dependencies=[Depends(require_admin)],
    tags=["admin"],
    summary="Get stored payment receipt info for a lead",
)
def admin_lead_receipt_info(lead_id: int, request: Request) -> ReceiptResponse:
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return serialize_receipt(request, lead)


@app.get(
    "/admin/leads/{lead_id}/receipt",
    dependencies=[Depends(require_admin)],
    tags=["admin"],
    summary="Open stored payment receipt for a lead",
)
def open_lead_receipt(lead_id: int) -> RedirectResponse:
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    receipt_file_id = lead.get("receipt_file_id")
    if not receipt_file_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return open_telegram_file(receipt_file_id)


@app.get(
    "/admin/leads",
    response_model=list[LeadResponse],
    dependencies=[Depends(require_admin)],
    tags=["admin"],
    summary="List all submitted leads",
)
def admin_leads(
    request: Request,
    payment_status: str | None = Query(default=None, description="Filter by payment status"),
) -> list[LeadResponse]:
    leads = list_leads()
    if payment_status:
        leads = [lead for lead in leads if lead["payment_status"] == payment_status]
    return [serialize_lead(request, lead) for lead in leads]


@app.get(
    "/admin/leads/{lead_id}",
    response_model=LeadResponse,
    dependencies=[Depends(require_admin)],
    tags=["admin"],
    summary="Get one submitted lead",
)
def admin_lead_detail(lead_id: int, request: Request) -> LeadResponse:
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return serialize_lead(request, lead)


@app.get(
    "/admin/stats",
    response_model=LeadStatsResponse,
    dependencies=[Depends(require_admin)],
    tags=["admin"],
    summary="Get lead counters for admin dashboard",
)
def admin_stats() -> LeadStatsResponse:
    leads = list_leads()
    total = len(leads)
    pending_payment = sum(1 for lead in leads if lead["payment_status"] == "pending")
    paid_payment = sum(1 for lead in leads if lead["payment_status"] == "paid")
    error_payment = sum(1 for lead in leads if lead["payment_status"] == "error")
    return LeadStatsResponse(
        total=total,
        pending_payment=pending_payment,
        paid_payment=paid_payment,
        error_payment=error_payment,
    )


@app.patch(
    "/admin/leads/{lead_id}/payment",
    response_model=MessageResponse,
    dependencies=[Depends(require_admin)],
    tags=["admin"],
    summary="Update lead payment method from admin panel",
)
def admin_lead_payment_update(lead_id: int, payload: PaymentUpdateRequest) -> MessageResponse:
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    update_payment_method(lead_id, payload.payment_method)
    return MessageResponse(status="updated")


@app.patch(
    "/admin/leads/{lead_id}/payment-status",
    response_model=MessageResponse,
    dependencies=[Depends(require_admin)],
    tags=["admin"],
    summary="Update lead payment status and notify user",
)
def admin_lead_payment_status_update(lead_id: int, payload: PaymentStatusUpdateRequest) -> MessageResponse:
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_payment_status(lead_id, payload.payment_status)

    if payload.payment_status == "paid":
        send_telegram_message(lead["telegram_chat_id"], "Тўловингиз муваффақиятли қабул қилинди")
    elif payload.payment_status == "error":
        send_telegram_message(lead["telegram_chat_id"], "Тўловни қайтадан текширинг")

    return MessageResponse(status=payload.payment_status)
