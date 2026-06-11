# W1 — Memoria di Team Consolidata
**Periodo:** 27 aprile – 3 maggio 2026
**Progetto:** AI-Powered Robo-Advisor Platform — Programming in Finance II 2026 (USI, Prof. Gruber)
**Design di riferimento:** smart single contract v2 (v3.1)

> Documento di memoria operativa: cosa ha fatto ciascuno in W1, decisioni rilevanti, dipendenze sbloccate/aperte, stato all'avvio di W2.
> Costruito a partire dai session log individuali del team (P1, P2, P3, P4).

---

## 0. Membri del team e identificativi GitHub

| Ruolo | Area | GitHub handle (dove noto) |
|------|-----|---------------------------|
| **P1** | Backend / Data Engineering | **Sabrina15072002** (utente di questo advisor) |
| **P2** | Quant / Portfolio Optimization | **emmaerba** |
| **P3** | ML / Risk Profiling | (handle non esplicitato nei log) |
| **P4** | Frontend / LLM / Docs | (handle non esplicitato nei log) |

> Nota: l'attribuzione `emmaerba = P2` è confermata dall'incrocio fra il log P1 del 28/04 (review della PR #2 `universe_config.py` di emmaerba) e il log P2 del 28/04 (autore della stessa PR #2 con review request a Sabrina15072002).

---

## 1. Stato finale W1 — sintesi per ruolo

### P1 — Backend / Data Engineering (Sabrina15072002)
**Stato:** ✅ W1 completata al 100% — tutti i deliverable in `main` con CI verde.

Deliverable consegnati:
- `.github/workflows/ci.yml` — GitHub Actions con lint (ruff) + pytest su push/PR
- `pyproject.toml` configurato (`line-length = 100`, `[tool.ruff.lint.isort] known-first-party = ["backend"]`, `[tool.ruff.lint.per-file-ignores]`)
- `tests/test_placeholder.py` — fix iniziale "collected 0 items"
- `backend/data/schema.sql` — DB schema v3.1 (tabelle `users`, `recommendations`, `market_data_snapshots` + indici, con i campi `ucits_tickers_used`, `fallback_tickers_applied`, `regulatory_context`, `etf_universe_version`, `market_data_hash`)
- `backend/data/loader.py` — `ValidatedDataLoader` completo: NaN gate, ffill, SHA-256 hash su `prices.to_csv()`, UCITS fallback logic, `DataQualityReport` con `to_dict()`
- `backend/data/snapshots.py` — funzioni `init_db()`, `save_market_snapshot()`, `save_recommendation()`, `get_latest_snapshot()`
- `tests/test_data_loader.py` — 2 test happy-path (`test_load_happy_path`, `test_ucits_fallback_triggered`) con mock `unittest.mock.patch` di `yf.download` (gestione bulk vs probe)
- **Branch protection** attiva su `main` (require PR + 1 review + CI verde)
- Review/merge PR #2 di emmaerba (universe_config) e PR #3 (ci.yml)
- Merge PR #9 `feature/p1-data-layer` → `main`

Bug fix reale trovato dai test in `loader.py`:
- `_resolve_tickers`: `close.isna().mean()` ritornava `Series` invece di scalare → `The truth value of a Series is ambiguous`. Fix applicato: `float(close.isna().mean().mean())`.

Decisioni P1:
- `ASSET_WEIGHT_MIN = 0.05` (corretto da `0.03` durante review della PR #2 di emmaerba per allineamento al design v3.1)
- `market_data_hash` = SHA-256 di `prices.to_csv()` per riproducibilità bit-a-bit
- Tutto il workflow su browser GitHub + github.dev (no git locale in W1)

### P2 — Quant / Portfolio Optimization (emmaerba)
**Stato:** ✅ W1 completata — 3/3 task chiusi.

Deliverable consegnati:
- `backend/data/universe_config.py` — universo UCITS-aware, 8 ETF, 4 cluster, dataclass `ETFDefinition` immutabile, `_validate_universe()` a import-time (≥3 UCITS, no duplicati, esattamente 8 ETF, 4 cluster) — PR #2, mergiata
- `backend/optimizer/hrp.py` — `OptimizationResult` TypedDict con `Literal["HRP", "MV", "BL"]` (corretto da `ERC` a `BL` dopo discussione con P1 in PR #4); campi: `algorithm`, `weights`, `expected_return`, `expected_volatility`, `sharpe_ratio`, `risk_contributions`, `optimizer_version`, `solver_status`, `ucits_tickers_used`, `fallback_tickers_applied`. Stub `compute_covariance` (Ledoit-Wolf) con assertions difensive e `NotImplementedError` esplicito — PR #4 mergiata
- `tests/test_optimizer.py` — 3 test strutturali (interfaccia `OptimizationResult`, AssertionError su input invalido, NotImplementedError su input valido) — PR #5 in attesa di review

Decisioni P2 / scelte di design:
- **`EFA`** mantiene stesso ticker primary e fallback (no UCITS equivalente con copertura yfinance adeguata)
- **`XEON.MI`** come cash EUR (anziché `BIL` USD) → coerenza per investitore EU, fallback `BIL`
- **`AGGH.MI`** come bond aggregate EUR-hedged (anziché `AGG` USD) → riduce rischio FX
- **ERC** è componente interno (tilt aggressivo + fallback regime), **BL** è algoritmo standalone esposto → `Literal["HRP", "MV", "BL"]`
- Workflow interamente da GitHub web (commit/edit/PR via browser)

### P3 — ML / Risk Profiling
**Stato:** ✅ W1 chiusa — questionario, scaffold ML pipeline e ADR-002 consegnati.

Deliverable consegnati:
- `docs/questionnaire_schema.md` — questionario 10 domande in 3 sezioni (Who You Are Financially / How You Invest / How You React), metodologia **Grable & Lytton (1999)**, scoring 0–30, confidence zones, override Q7 — PR #1
- `backend/ml/profiler/rule_based.py` (Phase A profiler) — type hints rigorosi, costanti nominate, docstring NumPy-style, funzioni pure; due fix da code review applicati:
  - Estratta `_compute_score_unchecked` privata per evitare doppia validazione nel path `profile_user → compute_score`
  - Normalizzazione `top_drivers` contro deviazione massima possibile (1.5 costante) — non quella osservata
  - PR #6 aperta verso `main`, in attesa di review P1
- `backend/ml/profiler/scf_pipeline.py` — scaffold completo: `load_scf()` (stub `NotImplementedError`), `select_features()`, `standardise_features()`, `build_pipeline()`. Type hints + docstring in inglese
- `docs/adr/ADR-002-scf-preprocessing.md` (in inglese) — 4 decisioni: versione SCF 2022, `implicate=1`, feature selection con mapping al questionario, uso obbligatorio di `WGT`
- `progetto_overview_narrativo.md` — documento italiano di orientamento personale (utile anche per la presentazione al prof.)
- PR `feature/p3-scf-pipeline` aperta, 3 commit, all checks passed

Decisioni P3:
- **Naming canonico profile_label**: `CONSERVATIVE / MODERATE / AGGRESSIVE` (EN, UPPER) — da propagare a P1 (`schema.sql`) e P4 (Ground Truth JSON)
- **Override Q7** = regola **hard MiFID II Art. 25** (confidence = 1.0, non probabilistica)
- **`top_drivers` Phase A** = euristica deterministica documentata; schema identico a Phase B (SHAP) → no refactor downstream
- **`ProfilerOutput` schema** identico a quello che produrrà il GBM in W3
- Verifica empirica del SCF 2022: 22.975 righe, 357 colonne. Scoperto che `RISKSCALE` **non esiste** nel Summary Extract → sostituito con `YESFINRISK` + `NOFINRISK`. Corrette `CASH → CASHLI`, rimossa `REAL`.
- `WGT` obbligatorio (sovra-campionamento famiglie ricche): 1 riga ≈ N famiglie reali (es. 3027.96)
- **Conflitto naming aperto** scoperto: `schema.sql` di P1 usava IT mentre il codice EN. Segnalato in PR #6 al team, in attesa di fix da P1

### P4 — Frontend / LLM / Docs
**Stato:** ✅ W1 completata — frontend scaffold, AGENTS.md, README, architecture, schemi GT, ADR-001.

Deliverable consegnati:
- `AGENTS.md` — 4 agenti (Code Review, Test Generation, Documentation, + agent_pr per criterio 5), workflow agentic, piano PR automatizzata via GitHub Actions + Claude API, Evidence Log pronto
- `frontend/app.py` — Streamlit scaffold con 4 pagine (Questionnaire, Profile Result, Portfolio Dashboard, Chat Advisor), `render_profile()` con `profile_label`, `confidence`, placeholder `top_drivers`, tab HRP/Markowitz, EU Investor Note placeholder, session_state per profilo
- `README.md` — header + badge, project structure, installation, usage flow, API docs (3 endpoint con esempi JSON), Technical Highlights table, EU Awareness, disclaimer, academic documentation section
- `docs/architecture.md` — data flow, component boundaries, LLM safety pipeline, failure modes, tabella ADR
- ADR placeholders: ADR-001, ADR-002, ADR-003, ADR-004 (vuoti, di intestazione)
- Rinomina `ADR-001-db-schema.md` (di P1, vuoto) → `ADR-005-db-schema.md` per evitare conflitto di numerazione → comunicato al team via commento PR
- Risolto merge conflict su `backend/data/loader.py` mantenendo versione di P1
- Fix lint `ruff F401` (rimosso `from typing import Optional`) in `loader.py`
- Merge PR #5 `feature/p4-docs` → `main` con CI verde
- `backend/schemas/ground_truth.py` — modelli **Pydantic v2** completi del Ground Truth JSON canonico v3.1: `Metadata`, `Profiler`, `Portfolio`, `RiskMetrics`, `ClusterStructure`, `StressScenarios`, `BacktestSummary`, `LLMConstraints`, `RegulatoryContext`, root `GroundTruthPayload`. `model_validator`, `Field` constraints, `build_allowed_numbers()` automatica
- `backend/schemas/mock_data.py` — `get_mock_payload()` per i 3 profili (conservative / balanced / aggressive), Phase A compliant
- `backend/schemas/__init__.py` — package exports
- `docs/adr/ADR-001-hrp-over-markowitz.md` — completo (matematica HRP 3 fasi, Ledoit-Wolf, Ward linkage, tilt per profilo, guardrail, alternative considerate, riferimenti bibliografici)
- Branch `feature/p4-llm-narrator` con tutto il sopra, pushato (PR da aprire in W2)

Decisioni P4:
- `architecture.md` differenziato dal `README.md` (developer interno vs utente esterno)
- `expected_annual_return = null` e `sharpe_ratio = null` esplicitamente per HRP (non produce stime puntuali affidabili) — scelta progettuale
- `allowed_numbers` auto-popolato da `build_allowed_numbers()` → no manutenzione manuale whitelist LLM
- `RegulatoryContext.profiler_us_centric_caveat = True` triggera Regola 9 del system prompt LLM
- Validator `currency_exposure_sums_to_one` allentato a USD + EUR ≤ 1.0 (CSPX.L è quotato GBP)
- `backend/schemas/` = **single source of truth** per Ground Truth JSON
- **Anticipato di 2 settimane** il task GT schema (era previsto W3)

---

## 2. Cronologia W1 — chi ha fatto cosa, giorno per giorno

### Lunedì 27 aprile (Mon)
- **P3** — questionario completo (`docs/questionnaire_schema.md`), branch `feature/p3-questionnaire-schema`, **PR #1** aperta verso `main`. Configurato Git locale.

### Martedì 28 aprile (Tue)
- **P1 (Sabrina)** — `ci.yml` + GitHub Actions verde; `schema.sql` v3.1; `loader.py` (`ValidatedDataLoader` completo); branch protection su `main`. Review PR #2 di emmaerba (corretto `ASSET_WEIGHT_MIN` 0.03→0.05). Merge PR #2 e PR #3.
- **P2 (emmaerba)** — `universe_config.py` (8 ETF, dataclass, integrity assertions); **PR #2** review request a Sabrina (P1). Successivamente, `OptimizationResult` TypedDict in `hrp.py` su `feature/p2-optimizer-scaffold`; **PR #4** aperta, fix lint ruff (anche `Optional` non usato in `loader.py` di P1), CI verde.
- **P3** — `rule_based.py` completo (Phase A) con 2 fix da review esterna; smoke test 14 boundary; **PR #6** aperta, scoperto conflitto naming IT/EN in `schema.sql` di P1, segnalato a P1 nella PR.
- **P4** — `AGENTS.md` (4 agenti); `frontend/app.py` scaffold con 4 pagine; `README.md` completo; risoluzione merge conflict su `loader.py`; fix lint `ruff F401`; **PR #5** `feature/p4-docs` → `main` mergiata con CI verde.

### Mercoledì 29 aprile (Wed)
- **P1 (Sabrina)** — `snapshots.py` (4 funzioni); `tests/test_data_loader.py` (2 test con mock `yf.download`); bug fix `_resolve_tickers` (`Series` vs scalare); aggiornamento `pyproject.toml` (`known-first-party`, `per-file-ignores`); **PR #9** `feature/p1-data-layer` → `main` mergiata; verifica `AGENTS.md`.
- **P2 (emmaerba)** — risposta al commento P1 su PR #4, correzione `Literal["HRP", "MV", "ERC"]` → `Literal["HRP", "MV", "BL"]`, merge PR #4. Stub `compute_covariance` Ledoit-Wolf in `hrp.py`; `tests/test_optimizer.py` (3 test); fix CI ruff (F821 + I001); **PR #5** P2 aperta su `feature/p2-hrp-optimizer`, in attesa di review.
- **P3** — `progetto_overview_narrativo.md`; `scf_pipeline.py` scaffold; verifica empirica diretta su `SCFP2022.csv` (Fed) → correzione colonne (`RISKSCALE` → `YESFINRISK`/`NOFINRISK`, `CASH` → `CASHLI`, rimossa `REAL`); `ADR-002-scf-preprocessing.md`; PR `feature/p3-scf-pipeline` aperta, all checks passed.
- **P4** — `docs/architecture.md` (differenziato dal README); placeholders ADR-001/002/003/004; rename `ADR-001-db-schema.md` di P1 → `ADR-005-db-schema.md`; PR `feature/p4-docs` con reviewer P1.

### Venerdì 1 maggio (Fri)
- **P4** — `backend/schemas/ground_truth.py` (Pydantic v2 completo); `mock_data.py` con `get_mock_payload()` per 3 profili; `__init__.py`; `ADR-001-hrp-over-markowitz.md` (matematica HRP completa); fix CI ruff (E501 + I001); branch `feature/p4-llm-narrator` pushato. Anticipato di 2 settimane il GT schema (era previsto W3).

> Domenica 3 maggio chiude la W1.

---

## 3. Pull Request — registro PR aperte/mergiate in W1

| PR | Branch | Autore | Stato | Contenuto |
|----|--------|--------|-------|-----------|
| #1 | `feature/p3-questionnaire-schema` | P3 | aperta verso main | `docs/questionnaire_schema.md` |
| #2 | `feature/p2-universe-config` | P2 (emmaerba) | **mergiata** | `universe_config.py` |
| #3 | (CI) | P1 (Sabrina) | **mergiata** | `ci.yml` GitHub Actions |
| #4 | `feature/p2-optimizer-scaffold` | P2 (emmaerba) | **mergiata** | `OptimizationResult` TypedDict |
| #5 (P4) | `feature/p4-docs` | P4 | **mergiata** | AGENTS.md, app.py, README, architecture, ADR placeholders |
| #5 (P2) | `feature/p2-hrp-optimizer` | P2 (emmaerba) | aperta, in attesa review | `compute_covariance` stub + 3 test |
| #6 | `feature/p3-rule-based-profiler` | P3 | aperta, in attesa review P1 | `rule_based.py` Phase A profiler |
| #9 | `feature/p1-data-layer` | P1 (Sabrina) | **mergiata** | `snapshots.py` + `test_data_loader.py` + bug fix |
| — | `feature/p3-scf-pipeline` | P3 | aperta, all checks passed | `scf_pipeline.py` + ADR-002 |
| — | `feature/p4-llm-narrator` | P4 | branch pushato, PR da aprire in W2 | `backend/schemas/*` + ADR-001 |

> Conflitto di numerazione PR P2/P4: entrambe le sequenze partono dai numeri locali nei rispettivi log (in particolare due PR diverse riportate come "#5"). Sequenza esatta da verificare su GitHub all'avvio W2.

---

## 4. Decisioni rilevanti consolidate (W1)

### Naming
- `profile_label` ∈ `{CONSERVATIVE, MODERATE, AGGRESSIVE}` (EN, UPPER) — deciso da P3, **da propagare a P1 (`schema.sql`) e P4 (GT JSON)**.

### Architettura algoritmi
- `OptimizationResult.algorithm: Literal["HRP", "MV", "BL"]` (no `ERC`, che è interno).
- HRP: 3 fasi (Ledoit-Wolf shrinkage, Ward linkage, recursive bisection), con tilt per profilo + guardrail (ADR-001 P4).
- HRP `expected_annual_return` e `sharpe_ratio` lasciati `null` (scelta esplicita: HRP non produce stime puntuali affidabili).

### Universo ETF (P2)
- 8 ETF, 4 cluster, ≥3 UCITS, `ASSET_WEIGHT_MIN = 0.05` (allineato a v3.1 dopo review P1).
- `EFA`: stesso ticker primary e fallback (gap UCITS).
- `XEON.MI` cash EUR primary, `BIL` fallback.
- `AGGH.MI` bond aggregate EUR-hedged primary.

### Risk profiling (P3)
- Metodologia: **Grable & Lytton (1999)** — citazione pronta.
- Override Q7 = regola hard **MiFID II Art. 25** (confidence = 1.0).
- SCF 2022: `implicate=1` (semplificazione vs Rubin's Rules), `WGT` obbligatorio, feature variabili binarie (`YESFINRISK`/`NOFINRISK`).

### Backend / DB (P1)
- `market_data_hash` = SHA-256 di `prices.to_csv()` per riproducibilità.
- Schema v3.1 con campi `ucits_tickers_used`, `fallback_tickers_applied`, `regulatory_context`, `etf_universe_version`.
- Branch protection: PR + 1 review + CI verde.
- Workflow su browser GitHub + github.dev (zero ambiente locale).

### Frontend / docs (P4)
- `backend/schemas/` = single source of truth per GT JSON.
- `architecture.md` separato dal `README.md` (developer vs utente).
- `allowed_numbers` auto-generato (separation of concerns LLM/backend).

### Convenzioni di codice
- Linter: **ruff** con `line-length = 100`, `[tool.ruff.lint.isort] known-first-party = ["backend"]`, `[tool.ruff.lint.per-file-ignores]`.
- Type hints rigorosi, docstring NumPy-style, funzioni pure quando possibile, defensive assertions a inizio funzioni pubbliche.

### ADR — stato e ownership
| ADR | Argomento | Owner | Stato |
|-----|-----------|-------|-------|
| ADR-001 | HRP over Markowitz | P4 | ✅ scritto |
| ADR-002 | SCF preprocessing | P3 | ✅ scritto |
| ADR-003 | (placeholder) | — | da definire |
| ADR-004 | (placeholder, ipotesi: Ledoit-Wolf shrinkage W4) | P2/P4 | da scrivere |
| ADR-005 | DB schema (SQLite vs PostgreSQL) | **P1 (Sabrina)** | placeholder, **da scrivere in W2** |

> ⚠️ Conflitto rilevato dal piano (`development_plan.pdf`): nelle istruzioni P1 il documento DB schema era previsto come `ADR-001-db-schema.md`. P4 lo ha rinominato in `ADR-005-db-schema.md` per evitare collisione con ADR-001 di P4 (HRP). **Questo è un conflitto da gerarchia delle fonti**: il piano dice ADR-001, lo stato attuale del repo dice ADR-005. Da chiarire all'inizio di W2.

---

## 5. Dipendenze fra ruoli — stato fine W1

### Sbloccate da P1 (Sabrina) per il resto del team
- `ValidatedDataLoader` + `DataQualityReport` → consumabili da P2 per HRP/MV
- `schema.sql` v3.1 + `snapshots.py` → DB pronto per persistere recommendations e snapshots
- CI verde + branch protection → infrastruttura di qualità per tutto il team

### Sbloccate da P2 (emmaerba)
- `universe_config.py` → consumato da P1 (`loader.py`), test suite, e prossimo `hrp.py`
- `OptimizationResult` TypedDict → contratto stabile per P1, P3, P4

### Sbloccate da P3
- `ProfilerOutput` schema → identico a Phase B (SHAP) per W3
- Override Q7 documentato come MiFID II hard rule

### Sbloccate da P4
- `backend/schemas/ground_truth.py` (Pydantic v2) → tutti i moduli importeranno da qui
- `architecture.md` + ADR-001 HRP → base per il PDF accademico

### ⚠️ Aperte / a rischio per W2
1. **Conflitto naming label IT/EN in `schema.sql` di P1**: segnalato da P3 in PR #6, **fix da P1 entro lunedì W2**.
2. **Numerazione ADR**: P4 ha rinominato `ADR-001-db-schema.md` di P1 in `ADR-005-db-schema.md`. P1 deve confermare/scrivere ADR-005 (o ADR-001) in W2.
3. **`rule_based.py` (P3) deve essere importabile entro lunedì W2** per sbloccare `/profile` di P1. Se in ritardo, P1 usa **stub a 3 cluster** (conservativo/bilanciato/aggressivo) — segnalare via issue GitHub.
4. **PR #6 di P3 (`rule_based.py`) e PR #5 di P2 (`compute_covariance`)** in attesa di review P1.
5. **PR `feature/p4-llm-narrator` da aprire in W2** (branch pushato ma PR non ancora aperta).

---

## 6. Stato W1 vs. piano P1 (development_plan.pdf)

Checklist W1 P1 al chiusura settimana:

| Task piano P1 | Stato |
|---------------|-------|
| Setup repo GitHub + struttura cartelle canonica | ✓ fatto |
| DB schema v3.1 (`recommendations`, `market_data_snapshots`, `users` con tutti i campi v3.1) | ✓ fatto |
| AGENTS.md bozza iniziale | ✓ fatto (P4 ha scritto la versione completa) |
| `ci.yml` (GitHub Actions: lint + pytest) | ✓ fatto, CI verde |
| `universe_config.py` UCITS-aware (8 ETF, primary + fallback) | ✓ fatto (P2 + review P1) |
| `ValidatedDataLoader` scaffold | ✓ fatto, **già completo** (anticipato vs. piano: completo va in W3) |
| `test_data_loader.py` happy path | ✓ fatto (anticipato di 2 settimane vs piano W3) |
| `snapshots.py` | ✓ fatto |

**P1 è in anticipo sul piano** rispetto a `ValidatedDataLoader` completo e ai test (in piano W3, già fatti in W1).

---

## 7. Note per il PDF accademico (raccolte da tutti i log)

Materiale già pronto da riusare nella documentazione LaTeX (5–8 pp):
- **Grable & Lytton (1999)** — base accademica del questionario (P3).
- **MiFID II Art. 25** — vincolo normativo override Q7 e suitability assessment (P3).
- **Guiso et al. (2018), Fed Reserve SCF 2022** — riferimenti SCF (P3).
- **Ledoit & Wolf (2004)** — shrinkage covariance (P2).
- **HRP 3 fasi** completa con matematica (P4 ADR-001).
- **`market_data_hash` SHA-256** → riproducibilità bit-a-bit (P1).
- **Tensione UCITS/US** documentata (gap `EFA`, `GLD`, `VNQ` senza UCITS equivalente liquido) — sezione Limitations (P2).
- **`AGGH.MI` vs `AGG`** → cluster bond riflette differenza FX nel dendrogram HRP (P2).
- **Cluster D (cash)** con `ASSET_WEIGHT_MIN = 0.05` → buffer di liquidità garantito (P2/P1).
- **Bug `_resolve_tickers`** trovato dai test → esempio concreto di valore dei test automatici (Sezione 7 Lessons Learned, P1).
- **Mock yfinance** come documentazione del contratto bulk vs probe (P1).
- **Risoluzione merge conflict + ruff lint** come esempio di workflow collaborativo (P4).
- **Pattern "Phase A always works"** in `frontend/app.py` con mock autonomi (P4).
- **`expected_annual_return = null`** scelta progettuale onesta su HRP (P4).
- **`build_allowed_numbers()`** = separation of concerns LLM/backend (P4).
- **CI-driven development** → tutto da log GitHub Actions, zero ambiente locale (P1).
- **Override Q7 hard rule vs `top_drivers` deterministico** = distinzione regolatoria vs algoritmica (P3).
- **`implicate=1`** = semplificazione vs Rubin's Rules → da documentare in Limitations (P3).
- **Rename ADR P4** = esempio coordinamento agentic in Lessons Learned (P4).

---

## 8. Avvio W2 — priorità immediate (incrocio fra log e piano)

### P1 (Sabrina) — priorità lunedì W2
1. **Verifica `rule_based.py` di P3** importabile (review/merge PR #6). Se non disponibile → **stub a 3 cluster**.
2. **Risolvi conflitto naming IT/EN in `schema.sql`** (segnalato da P3 in PR #6).
3. **Chiarisci numerazione ADR DB schema** (ADR-001 da piano vs ADR-005 da rename P4).
4. Avvia **FastAPI skeleton** (5 endpoint stub) su `feature/p1-fastapi-endpoints`.
5. Avvia **rate limiting + API key auth** (`slowapi`).
6. Scrivi **ADR-001 (o ADR-005) DB schema** (motivazione SQLite vs PostgreSQL).
7. Review pendenti: PR #5 P2 (`compute_covariance`), PR #6 P3 (`rule_based.py`), PR P3 `feature/p3-scf-pipeline`.

### P2 (emmaerba) — priorità W2
- Implementare `compute_covariance` reale con `pypfopt.CovarianceShrinkage(prices).ledoit_wolf()`.
- Completare `hrp.py` (log returns, clustering Ward, recursive bisection, profile tilt, box constraints).
- `risk_metrics.py`, `markowitz.py`.
- ≥3 test funzionali in `test_optimizer.py`.

### P3 — priorità W2
- Implementare `load_scf()` reale.
- `clustering.py` con K-Means/GMM, label assignment.
- Mettere `SCFP2022.csv` in `data/scf/` (o `.gitignore` + istruzioni README).
- `tests/test_profiler.py` con 6 casi limite (boundary 7/8, 9/10, 17/18, 21/22, Q7=a + override, all-equal).
- Esplorare MCP server custom per Criterio 5.

### P4 — priorità W2
- Aprire PR `feature/p4-llm-narrator` → `main`.
- Allineare `frontend/app.py` ai nuovi mock (`get_mock_payload()`).
- Questionario UI completo (7-10 domande Grable-Lytton).
- Pagina profilo con `confidence` + `top_drivers`.
- Dashboard portfolio con pesi e metriche base.
- Collegamento frontend ↔ output mock o API P1.

### ⚠️ Alert criterio 5 (AI Agents) — responsabilità P1
- `agent_pr.yml` ancora **non in repo**. Va sviluppato in W2/W3 al più tardi (deadline operativa W4).
- AGENTS.md già visibile dal giorno 1 (P4 lo ha scritto). Evidence Log da popolare quando agent_pr.yml gira.

---

*Documento di memoria operativa, generato consolidando i session log W1 di P1, P2, P3, P4. Da rileggere a inizio W2 per allineamento.*
