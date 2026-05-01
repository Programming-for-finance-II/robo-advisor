
-- Robo-Advisor DB Schema v3.1
-- Engine: SQLite (MVP) — migrate to PostgreSQL if time allows


PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------
-- Table: users
-- Stores basic user identity for recommendation linkage.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                  TEXT PRIMARY KEY,       -- UUID v4
    created_at          TEXT NOT NULL,          -- ISO 8601 UTC
    session_token       TEXT NOT NULL UNIQUE    -- ephemeral session key
);

-- -------------------------------------------------------------
-- Table: recommendations
-- Full audit trail for every portfolio recommendation.
-- Every field needed to reproduce a result bit-for-bit.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendations (
    id                          TEXT PRIMARY KEY,   -- UUID v4
    user_id                     TEXT NOT NULL REFERENCES users(id),
    created_at                  TEXT NOT NULL,       -- ISO 8601 UTC
    data_fetch_timestamp        TEXT NOT NULL,       -- ISO 8601 UTC

    -- Input snapshot
    questionnaire_snapshot      TEXT NOT NULL,       -- JSON string
    profile_label               TEXT NOT NULL CHECK (
                                    profile_label IN (
                                        'CONSERVATIVE', 'MODERATE', 'AGGRESSIVE'
                                    )
                                ),
    profile_confidence          REAL NOT NULL,
    profile_model_version       TEXT NOT NULL,       -- "rule_based_v1" | "gbm_scf_v1"

    -- Market data provenance
    tickers_used                TEXT NOT NULL,       -- JSON array (primary tickers)
    ucits_tickers_used          TEXT NOT NULL,       -- JSON array — v3.1
    fallback_tickers_applied    TEXT,                -- JSON array or NULL — v3.1
    etf_universe_version        TEXT NOT NULL DEFAULT 'v3.1',  -- v3.1
    data_window_start           TEXT NOT NULL,       -- ISO date
    data_window_end             TEXT NOT NULL,       -- ISO date
    market_data_hash            TEXT NOT NULL,       -- SHA-256 of prices CSV
    nan_count_pre_clean         INTEGER NOT NULL,
    nan_count_post_clean        INTEGER NOT NULL,

    -- Optimizer config
    optimizer_algo              TEXT NOT NULL DEFAULT 'HRP',
    optimizer_version           TEXT NOT NULL,
    linkage_method              TEXT NOT NULL DEFAULT 'ward',
    shrinkage_method            TEXT NOT NULL DEFAULT 'ledoit_wolf',
    tilt_applied                TEXT,                -- NULL | 'erc' | 'min_var'
    guardrails_applied          INTEGER NOT NULL,    -- 0/1 boolean

    -- Output weights
    weights_raw_hrp             TEXT NOT NULL,       -- JSON
    weights_final               TEXT NOT NULL,       -- JSON
    risk_metrics                TEXT NOT NULL,       -- JSON
    cluster_structure           TEXT NOT NULL,       -- JSON
    stress_scenarios            TEXT NOT NULL,       -- JSON

    -- Regulatory context — v3.1
    regulatory_context          TEXT,                -- JSON: EU Awareness metadata

    -- LLM audit
    llm_model                   TEXT NOT NULL,
    system_prompt_hash          TEXT NOT NULL,       -- SHA-256
    ground_truth_json_hash      TEXT NOT NULL,       -- SHA-256
    llm_response_raw            TEXT NOT NULL,
    llm_response_validated      TEXT NOT NULL,
    validator_version           TEXT NOT NULL,
    validator_flags             TEXT,                -- JSON array of flags
    retry_count                 INTEGER NOT NULL DEFAULT 0,

    -- Compliance
    -- Compliance
    disclaimer_shown            INTEGER NOT NULL DEFAULT 0,  -- 0/1 boolean
    disclaimer_text_hash        TEXT NOT NULL DEFAULT ''
);

-- -------------------------------------------------------------
-- Table: market_data_snapshots
-- Stores raw price data for bit-for-bit reproducibility.
-- yfinance may adjust historical data retroactively (splits,
-- dividends) — without snapshots, old recommendations cannot
-- be replicated exactly.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_data_snapshots (
    hash            TEXT PRIMARY KEY,   -- SHA-256 of prices CSV
    created_at      TEXT NOT NULL,      -- ISO 8601 UTC
    tickers         TEXT NOT NULL,      -- JSON array
    window_start    TEXT NOT NULL,      -- ISO date
    window_end      TEXT NOT NULL,      -- ISO date
    data_csv        TEXT NOT NULL       -- serialized prices (CSV string)
);

-- -------------------------------------------------------------
-- Indexes — performance and audit queries
-- -------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_rec_user_id
    ON recommendations(user_id);

CREATE INDEX IF NOT EXISTS idx_rec_created_at
    ON recommendations(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rec_market_data_hash
    ON recommendations(market_data_hash);

CREATE INDEX IF NOT EXISTS idx_rec_profile_label
    ON recommendations(profile_label);
