# CIVILAI

CIVILAI is a Flask-based intelligent urban problem management system for demonstrating a complete civic grievance workflow. The receiving desk in this project is a **simulated authority system for demonstration purposes**, not a real government service.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

The app listens on port 3000. The local default is SQLite; for Preview/production, set `DATABASE_URL` to the managed MySQL or PostgreSQL connection string. The app creates its tables and safe demo records on first start. MySQL URLs are handled through PyMySQL.

## Demo accounts

- Citizen: `citizen@civilai.local` / `Citizen123!`
- Admin: `a95381718@gmail.com` / `anand@9762`
- Authority: `desk@civilai.local` / `Authority123!`

These accounts are local demonstration fixtures and must be replaced or disabled for a real deployment.

The administrator entrance is `/admin/login`. It accepts only users with the `ADMIN` role and redirects to `/admin`. If a citizen is already signed in, opening the admin entrance is allowed; successful administrator credentials replace the citizen session with a fresh role-checked admin session. Signed-in administrators can change their password from the control room. A wrong administrator password can start the security-word recovery flow at `/admin/verify-security`; the security word is stored only as a secure hash and is rate-limited to five failed attempts per 15 minutes.

## Test

```bash
pytest -q
```

## Production

Use Render with a Python environment, PostgreSQL/Supabase `DATABASE_URL`, a strong `SECRET_KEY`, and a private `AUTHORITY_API_TOKEN`. Start with:

```bash
gunicorn 'civilai:create_app()'
```

For durable attachments, configure the storage service boundary in `civilai/services.py` for Supabase Storage. Do not rely on Render's local filesystem for production uploads. Free hosting can sleep and impose quotas; continuous uptime and unlimited storage are not guaranteed.

## Manual walkthrough

1. Sign in as the demo citizen.
2. Open Register complaint and describe a pothole or broken streetlight.
3. Request classification, review the suggested department, then save the complaint.
4. Submit it to the simulated authority receiver.
5. Open the receipt and complaint timeline.
6. Sign out and sign in as the authority desk; move the authority status through review/in progress/resolved.
7. Return to the citizen account and confirm the updated status.
8. Repeat a submission or use retry to confirm idempotent authority handling.
