# ADR-003 — Cloud Deployment Strategy

**Date:** 2026-05-12  
**Status:** Accepted  
**Owner:** P1 — Backend / Data Engineering

---

## Context

The AI-Powered Robo-Advisor Platform requires a cloud deployment accessible
to all team members and to the course evaluators. The deployment must:

- Serve the Streamlit frontend publicly via a stable URL
- Persist the SQLite audit trail database across restarts
- Support environment variables (secrets) for the Anthropic API key
- Be free or near-free for a university prototype
- Be reproducible locally via `docker-compose`

Two options were evaluated: **Streamlit Community Cloud** and **Railway**.

---

## Options Considered

### Option A — Streamlit Community Cloud (selected)

**Pros:**
- Free tier with no credit card required
- Direct GitHub integration — deploys automatically on push to `main`
- Native Streamlit support — no Docker or server configuration needed
- Environment variables configurable as secrets in the dashboard
- Stable public URL (`*.streamlit.app`)

**Cons:**
- SQLite persistence requires a mounted volume or external storage
- Limited compute (1 vCPU, 800 MB RAM) — sufficient for prototype
- No custom domain on free tier
- App sleeps after inactivity — cold start on first request

### Option B — Railway (fallback)

**Pros:**
- Supports any Docker-based deployment
- Persistent volumes available natively
- More flexible compute options

**Cons:**
- Requires credit card for free tier after trial
- More complex setup (Dockerfile + railway.toml required)
- Higher operational overhead for a university prototype

---

## Decision

**Streamlit Community Cloud** is selected as the primary deployment target.

Reasons:
1. Zero cost and zero credit card risk for a university prototype
2. Direct GitHub integration eliminates manual deployment steps
3. Native Streamlit support matches the frontend stack exactly
4. Environment variables as secrets satisfies the `ANTHROPIC_API_KEY`
   security requirement

**Railway** is documented as the fallback if Streamlit Cloud proves
insufficient (e.g. persistent volume limitations).

---

## SQLite Persistence

Streamlit Community Cloud does not provide a persistent volume by default.
The SQLite database (`robo_advisor.db`) is written to the app's working
directory, which resets on each redeploy.

**Accepted limitation for prototype scope:** the audit trail is not
persistent across deploys. For production, PostgreSQL (documented in
ADR-001) would be the correct solution.

**Mitigation:** `docker-compose.yml` provides full local reproducibility
with a persistent SQLite volume for development and evaluation.

---

## Consequences

- Streamlit app deployed at: `[URL to be added after deploy]`
- `ANTHROPIC_API_KEY` configured as secret in Streamlit Cloud dashboard
- `docker-compose.yml` available for local reproduction
- Railway remains documented as fallback — no implementation required
- SQLite reset on redeploy is a known and accepted limitation

---

## References

- ADR-001: DB Schema Choice (SQLite vs PostgreSQL)
- `docker-compose.yml` — local reproducibility
- Streamlit Community Cloud docs: https://docs.streamlit.io/deploy