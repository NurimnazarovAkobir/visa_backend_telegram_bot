# Visa Backend Telegram Bot

Minimal Telegram bot for UK seasonal work visa service with Uzbek and Russian language support.

## Setup

1. Create a virtual environment if needed.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create `.env` from `.env.example` and set `BOT_TOKEN` and `ADMIN_TOKEN`.
4. Run the bot:

```powershell
python bot.py
```

5. Run admin API with Swagger:

```powershell
uvicorn api:app --reload
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## Admin API usage

Swagger is admin-only. Login endpoint:

```text
POST /auth/login
```

Swagger UI flow:

1. Open `/docs`
2. Run `POST /auth/login`
3. In the `username` field, enter admin email
4. In the `password` field, enter admin password
5. Copy `access_token`
6. Click `Authorize` and paste:

```text
Bearer your_access_token
```

Available admin endpoints after login:

- `GET /admin/leads` - all user submissions from the bot
- `GET /admin/leads/{lead_id}` - one submission in detail
- `GET /admin/stats` - dashboard counters
- `PATCH /admin/leads/{lead_id}/payment` - update payment method if needed
