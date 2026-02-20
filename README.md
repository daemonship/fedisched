# Social Scheduler for Mastodon & Bluesky (Self-Hosted)

> Fediverse/ATProto users lack a simple, private way to schedule posts. Existing tools are cloud-based or tied to Twitter/X.

## What It Solves

Fediverse/ATProto users lack a simple, private way to schedule posts. Existing tools are cloud-based or tied to Twitter/X.

## Who It's For

Privacy-conscious professionals, indie makers, and community managers on decentralized social platforms.

## Tech Stack
- Backend: FastAPI, SQLModel (SQLite), APScheduler
- Frontend: Svelte, Vite
- Authentication: bcrypt, session cookies
- Encryption: Fernet (cryptography)
- Mastodon: Mastodon.py
- Bluesky: atproto SDK
- Deployment: Docker, Docker Compose

## Development Status

| Task | Status | Notes |
|------|--------|-------|
| 1. Initialize project skeleton and Docker Compose | ✅ Complete | FastAPI + Svelte scaffold, Dockerfile, docker-compose.yml, health endpoint, SQLModel schemas |
| 2. Single-user auth and credential encryption | ⬜ Pending | |
| 3. Mastodon OAuth flow and posting | ⬜ Pending | |
| 4. Bluesky auth and posting | ⬜ Pending | |
| 5. Composer UI, queue view, and scheduling interface | ⬜ Pending | |
| 6. Background scheduler and retry logic | ⬜ Pending | |
| 7. Code review | ⬜ Pending | |
| 8. Pre-launch verification | ⬜ Pending | |
| 9. Deploy to production | ⬜ Pending | |

## Quick Start

### Using Docker Compose (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/daemonship/fedisched.git
   cd fedisched
   ```

2. Copy `.env.example` to `.env` and edit:
   ```bash
   cp .env.example .env
   ```
   Generate a 32-byte base64 key for `SERVER_KEY` (e.g., `openssl rand -base64 32`).
   Set `SECRET_KEY` to a random string.

3. Start the container:
   ```bash
   docker-compose up -d
   ```

4. Open http://localhost:8000 in your browser.

### Development Setup

#### Backend
```bash
cd fedisched
python -m venv venv
source venv/bin/activate
pip install -e .
cp .env.example .env  # and fill values
uvicorn app.main:app --reload
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

The frontend will proxy API requests to `http://localhost:8000`.

## Project Structure

- `app/` – FastAPI backend
  - `main.py` – Application entry point
  - `config.py` – Environment configuration
  - `database.py` – SQLModel engine and session
  - `models.py` – SQLModel schemas (User, Account, ScheduledPost)
  - `api/` – API endpoints
- `frontend/` – Svelte SPA
- `pyproject.toml` – Python dependencies
- `Dockerfile` – Multi-stage container build
- `docker-compose.yml` – Compose configuration
- `.env.example` – Environment template

## License

MIT

---

*Built by [DaemonShip](https://github.com/daemonship) — autonomous venture studio*
