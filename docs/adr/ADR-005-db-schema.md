# ADR-005 — Database Schema: SQLite vs PostgreSQL

---

## Context

The platform needs a persistent audit trail for every portfolio recommendation
produced by the system. Each record must store enough information to reproduce
a recommendation bit-for-bit: the user's questionnaire snapshot, the market
data hash, the optimizer configuration, the LLM response, and the full set of
UCITS compliance fields introduced in design v3.1.

We needed to decide between SQLite and PostgreSQL before writing `schema.sql`
and `snapshots.py`, because the choice affects the connection logic, the deploy
strategy, and the test setup.

---

## Decision

We chose **SQLite** as the primary database for the MVP.

---

## Reasons

**1. Zero infrastructure overhead**  
SQLite is a file-based database — no server process, no connection string, no
Docker dependency. This matters for a four-week academic project where setup
time is a real cost. The entire DB is a single `.db` file that lives in the
repo volume.

**2. Compatible with Streamlit Community Cloud**  
Our primary deploy target (Streamlit Community Cloud) does not provide a
managed PostgreSQL instance. SQLite with a persisted volume is the simplest
path to a live URL, which is required for P4's chat page and for the final
demo. Railway (our fallback) also supports SQLite with a mounted volume.

**3. Sufficient for the expected load**  
This is a single-user academic demo, not a production system. SQLite handles
concurrent reads well and sequential writes without issue at this scale. We
do not expect concurrent write contention.

**4. Faster local development and testing**  
Tests can spin up an in-memory SQLite instance with no teardown. This keeps
the CI pipeline simple and fast — no test database to provision.

---

## Schema v3.1 — Key Tables

### `recommendations`
Full audit trail for every portfolio recommendation. Key fields:

| Field | Type | Purpose |
|-------|------|---------|
| `id` | TEXT (UUID v4) | Unique recommendation identifier |
| `market_data_hash` | TEXT (SHA-256) | Links to the exact price snapshot used — enables bit-for-bit reproducibility |
| `ucits_tickers_used` | TEXT (JSON array) | Tracks which tickers were UCITS-eligible at the time of the recommendation |
| `fallback_tickers_applied` | TEXT (JSON array or NULL) | Records when a US fallback ticker was used instead of the UCITS primary |
| `regulatory_context` | TEXT (JSON) | EU Awareness metadata: MiFID II disclaimer shown, profiler_us_centric_caveat flag |
| `etf_universe_version` | TEXT | Pinned to `v3.1` — ensures recommendations are traceable to a specific ETF universe |
| `profile_label` | TEXT | `CONSERVATIVE`, `MODERATE`, or `AGGRESSIVE` (EN UPPER — aligned with rule_based.py) |
| `system_prompt_hash` | TEXT (SHA-256) | Audit trail for the LLM prompt version used |

### `market_data_snapshots`
Stores the raw price CSV for each unique market data pull. The SHA-256 hash
of `prices.to_csv()` is the primary key, matching the `market_data_hash`
field in `recommendations`. This allows exact reproduction of any past
optimization even if yfinance retroactively adjusts historical prices
(stock splits, dividend corrections).

### `users`
Minimal user identity table — stores UUID + session token. No PII collected.

---

## Limitations

**No concurrent writes.**  
SQLite uses file-level locking. If two users submit a request simultaneously,
one will wait. Acceptable for a demo, not for production.

**No native JSON operators.**  
Fields like `ucits_tickers_used` and `regulatory_context` are stored as JSON
strings. PostgreSQL would allow indexing and querying inside these fields
natively (JSONB). In SQLite we deserialize in Python after fetching.

**Size limit.**  
SQLite databases above ~1 GB can show performance degradation. Not a concern
for this project.

**Portability.**  
Migration to PostgreSQL would require replacing the connection logic in
`snapshots.py` and adjusting a few SQLite-specific pragmas (`WAL mode`,
`PRAGMA foreign_keys`). The schema itself is ANSI SQL and portable.

---

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| PostgreSQL (cloud-managed) | Requires external service (e.g. Supabase, Neon), adds infra complexity, no free tier on Streamlit Cloud |
| PostgreSQL (Railway) | Railway free tier has storage limits and requires Docker Compose wiring — viable fallback but more setup |
| In-memory only (no persistence) | No audit trail — fails the v3.1 reproducibility requirement and criterion 2 of the grading rubric |

---

## Consequences

- `snapshots.py` uses Python's built-in `sqlite3` module — no ORM, no extra
  dependency.
- The `PRAGMA journal_mode = WAL` setting is enabled at DB init to allow
  concurrent reads while a write is in progress.
- If the project were to go to production, the migration path is:
  swap `sqlite3` for `psycopg2`, remove SQLite pragmas, deploy a managed
  PostgreSQL instance. The schema requires no changes.