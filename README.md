# Social Scheduler for Mastodon & Bluesky (Self-Hosted)

> Fediverse/ATProto users lack a simple, private way to schedule posts. Existing tools are cloud-based or tied to Twitter/X.

## Feedback & Ideas

> **This project is being built in public and we want to hear from you.**
> Found a bug? Have a feature idea? Something feel wrong or missing?
> **[Open an issue](../../issues)** — every piece of feedback directly shapes what gets built next.

## Status

> 🚧 In active development — not yet production ready

| Feature | Status | Notes |
|---------|--------|-------|
| Project scaffold & CI | ✅ Complete | FastAPI + Svelte, Docker, SQLModel schemas |
| Single-user auth & encryption | ✅ Complete | bcrypt, session cookies, Fernet credential encryption |
| Mastodon OAuth & posting | ✅ Complete | OAuth 2.0 flow, encrypted token storage, live token verification |
| Bluesky auth & posting | ✅ Complete | App password auth, session refresh, posting via AT Protocol |
| Composer UI & scheduling interface | ✅ Complete | Svelte SPA with per-platform character counters, queue view, retry |
| Background scheduler & retry logic | 📋 Planned | |
| Code review | 📋 Planned | |
| Pre-launch verification | 📋 Planned | |
| Deploy to production | 📋 Planned | |

## What It Solves

Privacy-conscious professionals, indie makers, and community managers on decentralized social platforms need a simple, private way to schedule posts — without handing credentials to a cloud service.

## Who It's For

Self-hosters who want full control: your posts, your server, your data.

## Tech Stack
- Backend: FastAPI, SQLModel (SQLite), APScheduler
- Frontend: Svelte, Vite
- Authentication: bcrypt, session cookies
- Encryption: Fernet (cryptography)
- Mastodon: Mastodon.py (OAuth 2.0)
- Bluesky: atproto SDK
- Deployment: Docker, Docker Compose

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
   Generate a 32-byte base64 key for `SERVER_KEY`:
   ```bash
   openssl rand -base64 32
   ```
   Set `SECRET_KEY` to a different random string.

3. Start the container:
   ```bash
   docker compose up -d
   ```

4. Open http://localhost:8000 in your browser and complete the setup wizard.

### Development Setup

#### Backend
```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in values
uvicorn app.main:app --reload
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

The frontend proxies API requests to `http://localhost:8000`.

## Connecting a Mastodon Account

1. Log in and navigate to the Accounts page.
2. Enter your Mastodon instance URL (e.g. `mastodon.social`).
3. You will be redirected to your instance to authorize Fedisched.
4. After approval, your account appears in the list — credentials are stored encrypted using your `SERVER_KEY`.

> **Callback URL:** The OAuth callback goes to `BACKEND_URL/api/accounts/mastodon/callback`. For local development this is `http://localhost:8000/api/accounts/mastodon/callback`. Set `BACKEND_URL` in `.env` to match your deployment URL in production.

## Backup & Recovery

Your data lives in a single SQLite file (`fedisched.db`, mounted at `/data/fedisched.db` inside the container).

**What to back up:**
- The SQLite database file from the Docker volume
- Your `.env` file — specifically `SERVER_KEY`, which is required to decrypt stored credentials

**If you lose `SERVER_KEY`:** The database itself is intact but all stored OAuth tokens and app passwords will be unreadable. You will need to reconnect all accounts after generating a new key.

**Moving to a new server:** Copy both the database file and `.env`, then `docker compose up -d`. No other steps required.

## Project Structure

```
app/
├── main.py            — Application entry point
├── config.py          — Environment configuration
├── database.py        — SQLModel engine and session
├── models.py          — SQLModel schemas (User, Account, ScheduledPost, MastodonOAuthState)
├── auth.py            — Authentication utilities (bcrypt, session cookies)
├── encryption.py      — Fernet encryption for stored credentials
├── platforms/
│   ├── mastodon.py    — Mastodon.py wrapper (OAuth, posting, token verification)
│   └── bluesky.py     — atproto SDK wrapper (app password auth, posting)
└── api/
    ├── auth.py        — Auth endpoints (setup wizard, login, logout)
    ├── accounts.py    — Account endpoints (Mastodon OAuth, Bluesky connect, listing, status)
    ├── posts.py       — Scheduled posts endpoints (create, list, retry, delete)
    └── health.py      — Health check endpoint
frontend/              — Svelte SPA with composer, queue, and account management
├── src/
│   ├── components/
│   │   ├── Navigation.svelte
│   │   ├── Composer.svelte    — Post composer with per-platform character counters
│   │   ├── Queue.svelte       — Scheduled posts queue with status badges
│   │   ├── Accounts.svelte    — Account connection and management
│   │   ├── Login.svelte
│   │   └── Setup.svelte
│   ├── lib/
│   │   ├── api.js             — API client
│   │   └── stores.js          — Svelte stores
│   ├── App.svelte
│   ├── main.js
│   └── app.css
tests/                 — pytest test suite (74 tests)
```

## License

MIT

---

*Built by [DaemonShip](https://github.com/daemonship) — autonomous venture studio*
