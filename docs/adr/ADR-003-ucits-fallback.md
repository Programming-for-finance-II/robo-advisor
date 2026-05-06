# ADR-003 — Cloud Deployment: Streamlit Community Cloud vs Railway

## Context

The platform needs a live public URL for the final demo and for P4's 
chat page integration tests. We needed to choose a deployment target 
before Week 4 to avoid last-minute infrastructure surprises.

Two options were evaluated: Streamlit Community Cloud and Railway.

---

## Decision

We chose **Streamlit Community Cloud** as the primary deployment target.
Railway is documented as the fallback.

---

## Reasons

**1. Zero cost**  
Streamlit Community Cloud is free for public GitHub repos with no 
credit card required. Railway has a free tier but with monthly usage 
limits that could be exceeded during demo and testing.

**2. Direct GitHub integration**  
Streamlit Cloud deploys automatically on every push to main. No 
Dockerfile, no CI configuration, no build pipeline needed. The app 
is live within minutes of a merge.

**3. Compatible with SQLite**  
Streamlit Cloud supports a persisted volume for SQLite. This means 
the audit trail DB survives between sessions without requiring a 
managed database service.

**4. No Docker required**  
The team has been working entirely in the browser (github.dev). 
Streamlit Cloud does not require Docker knowledge or a local 
environment — consistent with our CI-driven, browser-based workflow.

**5. Streamlit-native**  
The frontend is built with Streamlit. Deploying on Streamlit Cloud 
means the platform is optimised for Streamlit apps out of the box — 
no port configuration, no reverse proxy, no WSGI setup.

---

## Environment Variables

Secrets (ANTHROPIC_API_KEY and any future keys) are set via the 
Streamlit Cloud secrets manager — never committed to the repo. 
This satisfies the security requirement without a .env file or 
Docker secrets.

---

## Limitations

**No persistent background processes.**  
Streamlit Cloud runs the app as a single process. The FastAPI backend 
cannot run as a separate service on the same instance. For the demo, 
FastAPI is called in-process via httpx or directly imported — not as 
a separate server. This is acceptable for an academic prototype.

**Cold starts.**  
Streamlit Cloud apps spin down after inactivity. The first request 
after a period of inactivity may take 10-30 seconds to respond. 
Documented as a known limitation in the README.

**SQLite volume limitations.**  
The persisted volume is not a managed database. Concurrent write 
access is not supported. Acceptable for single-user demo purposes.

---

## Railway — Fallback

If Streamlit Cloud proves insufficient (e.g. cold start latency is 
unacceptable for the demo, or SQLite volume is unstable), Railway 
is the documented fallback:

| Criterion | Streamlit Cloud | Railway |
|-----------|----------------|---------|
| Cost | Free | Free tier (limited) |
| Docker required | No | Yes |
| GitHub integration | Direct | Via Dockerfile |
| SQLite support | Persisted volume | Mounted volume |
| Cold starts | Yes | No (paid tier) |
| Setup complexity | Low | Medium |

---

## Consequences

- `README.md` must include deployment instructions for Streamlit Cloud
- `ANTHROPIC_API_KEY` must be set as a secret in the Streamlit Cloud 
  dashboard before the first deploy
- `docker-compose.yml` (W4) documents the Railway fallback path for 
  local reproducibility
- If Railway is needed, a `Dockerfile` must be added — estimated 
  effort: 2-3 hours