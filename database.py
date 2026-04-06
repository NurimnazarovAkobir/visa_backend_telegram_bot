import sqlite3
import string
from secrets import choice
from pathlib import Path
from typing import Any


DB_PATH = Path("app.db")


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                telegram_user_id INTEGER NOT NULL,
                telegram_chat_id INTEGER NOT NULL,
                language TEXT NOT NULL,
                full_name TEXT NOT NULL,
                birth_date TEXT NOT NULL,
                has_passport TEXT,
                passport_series TEXT,
                russian_level TEXT NOT NULL,
                english_level TEXT,
                worked_in_england TEXT,
                travel_with TEXT,
                has_higher_education TEXT,
                has_driver_license TEXT,
                phone TEXT,
                interview_consent INTEGER DEFAULT 0,
                nationality TEXT NOT NULL DEFAULT '',
                agriculture_experience TEXT NOT NULL DEFAULT '',
                uk_seasonal_experience TEXT NOT NULL DEFAULT 'no',
                phone_primary TEXT NOT NULL DEFAULT '',
                phone_secondary TEXT,
                email TEXT NOT NULL,
                passport_file_id TEXT NOT NULL DEFAULT '',
                passport_kind TEXT NOT NULL DEFAULT '',
                payment_status TEXT NOT NULL DEFAULT 'pending',
                payment_method TEXT,
                receipt_file_id TEXT,
                receipt_kind TEXT,
                payment_started_at TEXT,
                abandoned_checkout_reminded_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(leads)").fetchall()
        }
        if "receipt_file_id" not in columns:
            connection.execute("ALTER TABLE leads ADD COLUMN receipt_file_id TEXT")
        if "receipt_kind" not in columns:
            connection.execute("ALTER TABLE leads ADD COLUMN receipt_kind TEXT")
        if "uk_seasonal_experience" not in columns:
            connection.execute(
                "ALTER TABLE leads ADD COLUMN uk_seasonal_experience TEXT NOT NULL DEFAULT 'no'"
            )
        if "payment_started_at" not in columns:
            connection.execute("ALTER TABLE leads ADD COLUMN payment_started_at TEXT")
        if "abandoned_checkout_reminded_at" not in columns:
            connection.execute("ALTER TABLE leads ADD COLUMN abandoned_checkout_reminded_at TEXT")
        lead_column_defaults = {
            "user_id": "INTEGER",
            "has_passport": "TEXT",
            "passport_series": "TEXT",
            "english_level": "TEXT",
            "worked_in_england": "TEXT",
            "travel_with": "TEXT",
            "has_higher_education": "TEXT",
            "has_driver_license": "TEXT",
            "phone": "TEXT",
            "interview_consent": "INTEGER DEFAULT 0",
        }
        for column_name, column_type in lead_column_defaults.items():
            if column_name not in columns:
                connection.execute(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                telegram_chat_id INTEGER NOT NULL,
                language TEXT,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                referral_code TEXT NOT NULL UNIQUE,
                referrer_user_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(referrer_user_id) REFERENCES users(telegram_user_id)
            )
            """
        )
        user_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "session_state" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN session_state TEXT")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS support_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                admin_message_id INTEGER,
                answer_text TEXT,
                answered_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(telegram_user_id) REFERENCES users(telegram_user_id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_referrer
            ON users(referrer_user_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_support_requests_user
            ON support_requests(telegram_user_id)
            """
        )


def generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(choice(alphabet) for _ in range(length))


def _unique_referral_code(connection: sqlite3.Connection) -> str:
    while True:
        code = generate_referral_code()
        row = connection.execute(
            "SELECT telegram_user_id FROM users WHERE referral_code = ?",
            (code,),
        ).fetchone()
        if not row:
            return code


def ensure_user(payload: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (payload["telegram_user_id"],),
        ).fetchone()

        if existing:
            current_referrer = existing["referrer_user_id"]
            next_referrer = current_referrer
            requested_referrer = payload.get("referrer_user_id")
            if current_referrer is None and requested_referrer not in {None, payload["telegram_user_id"]}:
                next_referrer = requested_referrer

            connection.execute(
                """
                UPDATE users
                SET telegram_chat_id = ?,
                    language = COALESCE(?, language),
                    username = ?,
                    first_name = ?,
                    last_name = ?,
                    referrer_user_id = ?,
                    session_state = COALESCE(?, session_state),
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (
                    payload["telegram_chat_id"],
                    payload.get("language"),
                    payload.get("username"),
                    payload.get("first_name"),
                    payload.get("last_name"),
                    next_referrer,
                    payload.get("session_state"),
                    payload["telegram_user_id"],
                ),
            )
        else:
            connection.execute(
                """
                INSERT INTO users (
                    telegram_user_id,
                    telegram_chat_id,
                    language,
                    username,
                    first_name,
                    last_name,
                    referral_code,
                    referrer_user_id,
                    session_state
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["telegram_user_id"],
                    payload["telegram_chat_id"],
                    payload.get("language"),
                    payload.get("username"),
                    payload.get("first_name"),
                    payload.get("last_name"),
                    _unique_referral_code(connection),
                    payload.get("referrer_user_id"),
                    payload.get("session_state"),
                ),
            )

        row = connection.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (payload["telegram_user_id"],),
        ).fetchone()
        return dict(row)


def get_user(telegram_user_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_referral_code(referral_code: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE referral_code = ?",
            (referral_code,),
        ).fetchone()
        return dict(row) if row else None


def get_referral_count(telegram_user_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM users WHERE referrer_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return int(row["total"]) if row else 0


def create_support_request(telegram_user_id: int, question_text: str) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO support_requests (
                telegram_user_id,
                question_text
            )
            VALUES (?, ?)
            """,
            (telegram_user_id, question_text),
        )
        return int(cursor.lastrowid)


def get_support_request(request_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM support_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        return dict(row) if row else None


def set_support_admin_message(request_id: int, admin_message_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE support_requests
            SET admin_message_id = ?
            WHERE id = ?
            """,
            (admin_message_id, request_id),
        )


def answer_support_request(request_id: int, answer_text: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE support_requests
            SET status = 'answered',
                answer_text = ?,
                answered_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (answer_text, request_id),
        )


def create_lead(payload: dict[str, Any]) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO leads (
                user_id,
                telegram_user_id,
                telegram_chat_id,
                language,
                full_name,
                birth_date,
                has_passport,
                passport_series,
                russian_level,
                english_level,
                worked_in_england,
                travel_with,
                has_higher_education,
                has_driver_license,
                phone,
                interview_consent,
                nationality,
                agriculture_experience,
                uk_seasonal_experience,
                phone_primary,
                phone_secondary,
                email,
                passport_file_id,
                passport_kind,
                payment_status,
                payment_method,
                receipt_file_id,
                receipt_kind
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("user_id", payload["telegram_user_id"]),
                payload["telegram_user_id"],
                payload["telegram_chat_id"],
                payload["language"],
                payload["full_name"],
                payload["birth_date"],
                payload.get("has_passport"),
                payload.get("passport_series"),
                payload["russian_level"],
                payload.get("english_level"),
                payload.get("worked_in_england"),
                payload.get("travel_with"),
                payload.get("has_higher_education"),
                payload.get("has_driver_license"),
                payload.get("phone"),
                payload.get("interview_consent", 0),
                payload.get("nationality", ""),
                payload.get("agriculture_experience", ""),
                payload.get("uk_seasonal_experience", payload.get("worked_in_england", "no")),
                payload.get("phone_primary", payload.get("phone", "")),
                payload.get("phone_secondary"),
                payload["email"],
                payload.get("passport_file_id", ""),
                payload.get("passport_kind", ""),
                payload.get("payment_status", "pending"),
                payload.get("payment_method"),
                payload.get("receipt_file_id"),
                payload.get("receipt_kind"),
            ),
        )
        return int(cursor.lastrowid)


def update_lead(lead_id: int, payload: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE leads
            SET user_id = ?,
                telegram_user_id = ?,
                telegram_chat_id = ?,
                language = ?,
                full_name = ?,
                birth_date = ?,
                has_passport = ?,
                passport_series = ?,
                russian_level = ?,
                english_level = ?,
                worked_in_england = ?,
                travel_with = ?,
                has_higher_education = ?,
                has_driver_license = ?,
                phone = ?,
                interview_consent = ?,
                nationality = ?,
                phone_primary = ?,
                email = ?,
                payment_status = ?,
                payment_method = COALESCE(payment_method, ?)
            WHERE id = ?
            """,
            (
                payload.get("user_id", payload["telegram_user_id"]),
                payload["telegram_user_id"],
                payload["telegram_chat_id"],
                payload["language"],
                payload["full_name"],
                payload["birth_date"],
                payload.get("has_passport"),
                payload.get("passport_series"),
                payload["russian_level"],
                payload.get("english_level"),
                payload.get("worked_in_england"),
                payload.get("travel_with"),
                payload.get("has_higher_education"),
                payload.get("has_driver_license"),
                payload.get("phone"),
                payload.get("interview_consent", 0),
                payload.get("nationality", ""),
                payload.get("phone_primary", payload.get("phone", "")),
                payload["email"],
                payload.get("payment_status", "pending"),
                payload.get("payment_method"),
                lead_id,
            ),
        )


def list_leads() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM leads ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_lead(lead_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()
        return dict(row) if row else None


def get_latest_payment_lead(telegram_user_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM leads
            WHERE telegram_user_id = ?
              AND payment_method IS NOT NULL
              AND receipt_file_id IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_user_id,),
        ).fetchone()
        return dict(row) if row else None


def update_payment_method(lead_id: int, payment_method: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE leads
            SET payment_method = ?,
                payment_started_at = COALESCE(payment_started_at, CURRENT_TIMESTAMP),
                abandoned_checkout_reminded_at = NULL
            WHERE id = ?
            """,
            (payment_method, lead_id),
        )


def attach_payment_receipt(lead_id: int, receipt_file_id: str, receipt_kind: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE leads
            SET receipt_file_id = ?,
                receipt_kind = ?,
                abandoned_checkout_reminded_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (receipt_file_id, receipt_kind, lead_id),
        )


def update_payment_status(lead_id: int, payment_status: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE leads
            SET payment_status = ?,
                abandoned_checkout_reminded_at = CASE
                    WHEN ? = 'pending' THEN abandoned_checkout_reminded_at
                    ELSE CURRENT_TIMESTAMP
                END
            WHERE id = ?
            """,
            (payment_status, payment_status, lead_id),
        )


def list_due_abandoned_checkout_leads() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM leads
            WHERE payment_method IS NOT NULL
              AND payment_status = 'pending'
              AND receipt_file_id IS NULL
              AND payment_started_at IS NOT NULL
              AND abandoned_checkout_reminded_at IS NULL
              AND datetime(payment_started_at, '+24 hours') <= CURRENT_TIMESTAMP
            ORDER BY id ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def mark_abandoned_checkout_reminded(lead_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE leads
            SET abandoned_checkout_reminded_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (lead_id,),
        )


def save_user_session(telegram_user_id: int, session_state: str | None) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET session_state = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = ?
            """,
            (session_state, telegram_user_id),
        )
