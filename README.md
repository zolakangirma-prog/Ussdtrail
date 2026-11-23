# Training Simulator licensing server

## Run on a trusted Linux host
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env`; set a BotFather token, admin Telegram numeric IDs, and a long random ADMIN_API_TOKEN.
4. Run API: `uvicorn main:app --host 127.0.0.1 --port 8000`
5. In another terminal run bot: `python bot.py`
6. Put a reverse proxy with a valid TLS certificate in front of port 8000. Set Android API_BASE to that HTTPS origin.

The Telegram bot token and ADMIN_API_TOKEN belong only on the server. Never put either in the APK. The first redemption binds a pending Telegram-generated code to one Android device. A code is one-time.

## Android configuration
Set `ActivationManager.API_BASE` to your HTTPS base URL and replace `YOUR_BOT_USERNAME` in `ActivationDialog.java`. Build with your existing Android Gradle setup.

## API
- `POST /api/activation/validate`: `{code, app_id, device_id}`
- `POST /api/license/status`: `{app_id, device_id}` + device Bearer token
- `POST /api/license/consume`: `{app_id, device_id, request_id}` + device Bearer token
- `POST /api/admin/revoke/{license_id}` + admin Bearer token

For production, use PostgreSQL, HTTPS-only reverse proxy, backups, monitoring, stronger per-device authentication (Android Play Integrity where available), and rate limiting at the proxy. The sample uses SQLite and is a functional starter, not a hardened commercial licensing platform.
