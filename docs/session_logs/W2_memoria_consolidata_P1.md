# W2 — Memoria Consolidata (4 → 10 maggio 2026)
**Owner del documento:** P1 — Backend / Data Engineering (Sabrina)
**Periodo coperto:** Settimana 2 del piano (4 maggio – 10 maggio 2026), con coda fino all'11 maggio per il merge di P3
**Scopo:** baseline di memoria per ripartire in W3 senza perdere contesto su decisioni, deliverable, dipendenze e criticità aperte.

---

## 1. Stato esecutivo a fine W2

W2 si chiude **in linea con il piano e con buffer parziale su W3**. P1 ha consegnato due milestone chiave (`/profile` live + `/optimize` live con pipeline end-to-end) e due ADR (W2 anticipato + W3 anticipato). Tutti gli altri P hanno consegnato il loro core deliverable W2:
- P1: `/profile` + `/optimize` endpoint, DB audit trail funzionante, 2 ADR
- P2 (Emma): `hrp.py` completo con Ledoit-Wolf, fix annualizzazione volatilità, 3 test funzionali
- P3 (Matteo): `clustering.py` su SCF 2022, parquet `scf_labeled` pronto per GBM W3 (merge l'11 mag)
- P4 (Elena): `system_prompt.py`, `NarratorClient`, questionario Streamlit 10 domande, skeleton LaTeX `report.tex`

CI verde su tutte le PR aperte alla chiusura W2.

---

## 2. Cosa ho fatto io (P1) in W2

### Lunedì 4 maggio
- **Fix `schema.sql`:** label italiani (`Conservativo`/`Bilanciato`/`Aggressivo`) → EN UPPER (`CONSERVATIVE`/`MODERATE`/`AGGRESSIVE`), allineato al contratto canonico v3.1 deciso con P3
- **Review post-hoc `rule_based.py` di P3** (PR #6 già merged): verificato importabilità, EN UPPER labels, Q7 override MiFID II, schema `ProfilerOutput`, assenza import circolari → OK
- **`backend/api/main.py` — FastAPI app con `/profile` endpoint:**
  - Pydantic request/response models con type hints completi
  - Rate limiting `slowapi`: 20 req/min
  - `ValueError` profiler → HTTP 422
  - Fix lint ruff I001
- **`tests/test_api.py` — 9 integration test su `/profile`:**
  - Happy path: CONSERVATIVE / MODERATE / AGGRESSIVE
  - Q7 MiFID II hard override
  - Response schema completo
  - Borderline confidence (score=9 → confidence=0.7, low_confidence_flag=True)
  - Error handling: chiave mancante / lettera invalida / risposta vuota
- **`docs/adr/ADR-005-db-schema.md`:** SQLite vs PostgreSQL, schema v3.1, campi chiave, limitazioni → merged

### Martedì 5 maggio
- **Review `hrp.py` di Emma — 3 divergenze identificate:**
  1. `BALANCED` → `MODERATE` (bloccante) — fixato da Emma prima del wire
  2. `expected_return`/`sharpe_ratio` ancora `float` invece di `Optional[float]` (non bloccante)
  3. `ASSET_MIN = 0.03` in `hrp.py` vs `ASSET_WEIGHT_MIN = 0.05` in `universe_config.py` (non bloccante)
  → Issue GitHub aperta; entrambi i non-bloccanti chiusi da Emma il 7 mag
- **Review PR `test_profiler.py` di P3:** rimossa duplicazione `[dependency-groups]` in `pyproject.toml` (conflitto con `[project.optional-dependencies]`, due versioni diverse di ruff)
- **Wire `/optimize` endpoint:**
  - Risolve ticker via `get_primary_tickers()` o override da request
  - Carica prezzi via `ValidatedDataLoader` con UCITS fallback
  - Chiama `optimize()` di P2 (HRP + Ledoit-Wolf + profile tilt + box constraints)
  - Persiste in DB via `snapshots.py` (`save_market_snapshot` + `save_recommendation`)
  - **DB failure non blocca la response** — log warning e continua (availability over consistency)
  - `OptimizeRequest` / `OptimizeResponse` Pydantic models
- **Fix ruff:** I001 (import order) e F401 (`logging` non usato a livello modulo, usato in except → import locale)
- **`docs/adr/ADR-003-cloud-deploy.md`** committato su `feature/p1-docs` (anticipo rispetto al piano W3)

---

## 3. Deliverable W2 di P1 vs piano (development_plan.pdf)

| Task pianificato W2 | Stato | Note |
|---|---|---|
| FastAPI skeleton 5 endpoint (`/profile` `/optimize` `/compare` `/advice` `/backtest`) | ✓ parziale | `/profile` e `/optimize` live. `/compare` `/advice` `/backtest` ancora stub o assenti |
| Rate limiting `slowapi` + API key auth | ▶ parziale | `slowapi` 20 req/min applicato; **API key header auth non ancora implementata** |
| `/profile` endpoint con `rule_based.py` di P3 | ✓ | P3 ha consegnato in anticipo (PR #6 merged) → no stub necessario |
| `snapshots.py` audit trail | ✓ | Funzionante end-to-end nel wire `/optimize` (anticipo rispetto a piano Fri-Sun W2) |
| `ADR-001-db-schema.md` | ✓ | Consegnato come `ADR-005-db-schema.md` — **verificare se la numerazione è coerente con il dev plan** (in development_plan.pdf l'ADR DB è `ADR-001`) |

⚠ **Punto da chiarire:** la numerazione ADR. Il piano cita ADR-001 (DB) e ADR-003 (cloud). Io ho usato ADR-005 e ADR-003. Da riconciliare in W3 per non confondere chi legge la doc accademica.

---

## 4. Cosa hanno consegnato gli altri P (rilevante per P1)

### P2 — Emma (Quant/Optimizer)
- `hrp.py` completo: log returns, Ledoit-Wolf via `PyPortfolioOpt` (`CovarianceShrinkage`), Ward clustering, recursive bisection, profile tilt, box constraints
- **Bug fixato (importante):** doppia annualizzazione volatilità → ora `CovarianceShrinkage(prices, frequency=1)` + `* 252` esplicito in `optimize()`. Senza fix, la vol nel Ground Truth JSON sarebbe gonfiata di √252 ≈ 15.87x
- `OptimizationResult.expected_return: float | None` e `sharpe_ratio: float | None` (fix dei due punti non-bloccanti che avevo segnalato)
- `_compute_erc_weights` usa inverse volatility weighting (approssimazione ERC, no μ)
- 9 test totali in `test_optimizer.py` (3 strutturali W1 + 3 funzionali W2 + 3 contract/regression)
- Single source of truth: box constraints importate da `universe_config.py`

→ **Input pronto per P1:** `optimize()` callable e stabile. Il wire `/optimize` già usa questa interfaccia.

### P3 — Matteo (ML/Profiling)
- `rule_based.py` consegnato in W1/W2 (PR #6 merged) → ha sbloccato `/profile` senza bisogno di stub
- `clustering.py` su SCF 2022 (implicate=1, n=4595): K-Means 3 cluster su allocation ratios normalizzati, silhouette score, label deterministico per mean equity ratio
- Distribuzione cluster: AGGRESSIVE 59.2% / CONSERVATIVE 34.3% / MODERATE 6.5% (skew dovuto a oversampling SCF dei top wealth percentiles — documentato)
- **Bug fix critico:** `build_pipeline()` ora restituisce anche `df_selected` (feature demografiche), non solo `alloc`. Senza questo fix il parquet `scf_labeled.parquet` non avrebbe avuto X per il training GBM in W3
- PR `feature/p3-clustering` merged 11 maggio

→ **Input atteso per P1 in W3:** GBM trainato + SHAP integration → `/profile` Phase B (al momento `/profile` usa solo `rule_based.py`, Phase A)

### P4 — Elena (Frontend/LLM)
- `backend/llm/prompts/system_prompt.py`: 9 regole del design v3.1 (inclusa Rule 9 EU Awareness), `MANDATORY_DISCLAIMER` come costante condivisa
- `backend/llm/narrator.py` — `NarratorClient`: stateless, `temperature=0.0`, injection defence Layer 1 (length check + 14 pattern), SHA-256 audit hashes
- Questionario Streamlit 10 domande Grable & Lytton + dashboard collegata al `session_state["profile"]`
- Fix issue #28: `RiskMetrics.expected_annual_return` e `sharpe_ratio` → `Optional[float]` (allineamento con `OptimizationResult` di P2)
- **`docs/report.tex` skeleton LaTeX completo** con 8 sezioni + `references.bib` con 4 citazioni base (López de Prado 2016, Ledoit-Wolf 2004, SCF 2022, MiFID II) — anticipo rispetto al piano W4

→ **Input atteso per P1 in W3:** `validator.py` (già consegnato il 9 mag, fuori W2) per il wire `/advice`

---

## 5. Stato dipendenze critiche (mappa P1-centric)

### IN INGRESSO su P1
| Da | Cosa | Atteso entro | Stato |
|---|---|---|---|
| P3 | `rule_based.py` importabile | Lunedì W2 | ✓ consegnato in W1 (PR #6) — `/profile` Phase A live senza stub |
| P3 | GBM + SHAP per `/profile` Phase B | W3 | ⏳ in progress (parquet pronto post-merge 11 mag) |
| P2 | `optimize()` callable | Martedì W2 | ✓ consegnato, wired |
| P2 | `run_backtest()` | W3 | ⏳ atteso (P2 ha scenari GFC 2008 / COVID 2020 / Rate Hike 2022 pianificati) |
| P4 | `validator.py` per wire `/advice` | W3 | ✓ consegnato il 9 mag (27/27 test verdi) |

### IN USCITA da P1
| A | Cosa | Stato |
|---|---|---|
| P3 | `/profile` endpoint live → P3 può integrare Phase B | ✓ disponibile |
| P4 | `/profile` endpoint per chat page | ✓ disponibile |
| P2 | `/optimize` + `ValidatedDataLoader` per dati mercato | ✓ entrambi live |
| P4 | `/advice` endpoint per chat LLM | ✗ ancora stub 503 — sblocco W3 |
| P2 | `/backtest` endpoint | ✗ da implementare W3 |
| Team | `agent_pr.yml` + URL PR per AGENTS.md evidence (Criterio 5) | ✗ **non ancora aperto** — alert permanente |

---

## 6. Criticità aperte da gestire in W3

### 🔴 Alta priorità

1. **`agent_pr.yml` non aperto** — Criterio 5 (AI Agents) è obbligatorio per il voto. Il piano lo mette in W4 ma è opportuno aprire almeno uno **stub funzionante in W3** per de-riskare. P1 è l'owner tecnico. Senza la PR automatica visibile su GitHub, P4 non può popolare l'Evidence Log in AGENTS.md.

2. **Endpoint mancanti / da completare:** `/compare`, `/advice`, `/backtest`. Il piano li ha nel range W2 (skeleton) + W3 (wire). Ad oggi P1 ha solo `/profile` e `/optimize`.

3. **API key header auth non implementata** — il piano W2 la richiede insieme a `slowapi`. È un task piccolo (header `X-API-Key` + dependency in FastAPI) ma va chiuso prima del deploy W4.

4. **Numerazione ADR incoerente con dev plan** — il piano usa `ADR-001-db-schema.md`, io ho prodotto `ADR-005-db-schema.md`. Da riconciliare: o rinomino, o aggiorno il piano. Prima di scrivere il PDF accademico questo va sistemato.

### 🟡 Media priorità

5. **Integration test suite incompleta:** il piano W3 prevede `test_data_loader.py`, `test_optimizer.py` end-to-end (con dati yfinance reali, non synthetic), verifica di tutti gli endpoint. Al momento esistono `test_api.py` (9 test, P1) e `test_optimizer.py` (9 test, P2).

6. **ValidatedDataLoader scaffold vs implementazione effettiva:** verificare lo stato — il piano W3 chiede la versione completa (NaN gate, ffill, hash, **UCITS fallback effettivo**, non solo scaffold). Il wire `/optimize` la chiama, ma serve confermare che tutti i path siano testati con dati reali.

7. **`test_ucits_fallback.py`** (W4, shared con P3) — ≥3 test cases: triggers su DataFrame vuoto, `fallback_tickers_applied` popolato in `DataQualityReport`, DB row registra il fallback. Pianificare l'inizio in W3 tardi.

### 🟢 Bassa priorità / monitoraggio

8. **Branch hygiene:** problema dei branch "83 commits behind" su github.dev — workaround usato è creare branch da `main` su github.com. Da ricordare se si torna a github.dev.

9. **Inconsistenza documentale `0.03` vs `0.05`** (segnalata da Emma): la checklist P0 in `versione 2- smart single portfolio` riporta ancora `0.03` mentre codice + GT JSON usano `0.05`. Da correggere prima del PDF accademico.

---

## 7. Decisioni tecniche W2 da ricordare (con razionale)

| Decisione | Razionale | Citabile nel PDF? |
|---|---|---|
| **DB failure non blocca la response di `/optimize`** | Availability over consistency in prototipo accademico — l'utente riceve sempre il portafoglio; il DB è best-effort | Sì, Sezione architettura |
| **Validate at the boundary** (Pydantic + `ValueError` → HTTP 422) | API design difensivo, errore di dominio mappato esplicitamente a codice HTTP semantico | Sì, Sezione architettura backend |
| **Stub first, wire later** per `/optimize` | Sviluppo parallelo P1/P2 senza blocco reciproco; documentato in commento `main.py` per il prof | Sì, Lessons Learned |
| **`OptimizationResult.expected_return: Optional[float]`** | HRP è covariance-only (López de Prado 2016) — non stima μ; il tipo lo documenta in modo verificabile dai test | Sì, Sezione Portfolio Optimization |
| **`CovarianceShrinkage(frequency=1)` + `* 252` esplicito** | Single point of annualization → evita doppio scaling. Senza fix, vol gonfiata ×15.87 | Sì, Lessons Learned (bug history) |
| **Single source of truth per box constraints** (`universe_config.py`) | Previene drift cross-modulo, replicabile per `markowitz.py` | Sì, Sezione Coding Structure |
| **Borderline confidence test (score=9 → 0.7 + flag)** | Propaga segnale di incertezza del profiler fino al layer HTTP | Sì, Sezione ML Risk Profiler |

---

## 8. PR e CI a chiusura W2

Stato visto nei log:
- `feature/p1-fastapi-endpoints` — `/profile` wire + 9 test → **merged** in main
- `feature/p1-fastapi-endpoints` (continuazione) — `/optimize` wire → **merged** in main
- `feature/p1-docs` — ADR-005 DB + ADR-003 cloud → ADR-005 **merged**, ADR-003 da verificare
- `feature/p2-hrp-optimizer-1` — Emma, hrp + 3 test funzionali → CI verde, attesa review
- `feature/p3-clustering` — Matteo → **merged 11 maggio**
- `feature/p4-llm-narrator` — Elena, narrator + system_prompt + validator → CI verde, in attesa di review (P4 chiede review a P1)

⚠ **Azione P1 W3:** review PR `feature/p4-llm-narrator` (Elena la richiede esplicitamente).

---

## 9. Piano W3 (11–17 maggio) — vista P1

Dal dev plan + criticità accumulate:

**Mon–Tue (oggi-domani):**
- Implementare wire `/advice` endpoint usando `NarratorClient` (P4) + `validate()` (P4) — sblocca chat page P4
- Iniziare scaffold `agent_pr.yml` (de-rischio Criterio 5)
- Review PR `feature/p4-llm-narrator`

**Wed–Thu:**
- `ValidatedDataLoader` completo e testato (NaN gate, ffill, hash, UCITS fallback **effettivo**)
- `test_data_loader.py` con dati reali yfinance (≥1 anno history)
- Wire `/backtest` quando P2 consegna `run_backtest()`
- `/compare` endpoint

**Fri:**
- `ADR-003-cloud-deploy.md` finalizzato (se non già merged)
- Riconciliazione numerazione ADR
- API key header auth

**Sat–Sun:**
- Buffer / verifica integration test suite completa / preparazione deploy W4

---

## 10. Note per il PDF accademico (raccolte da W2)

- **Bug history come Lessons Learned:** doppia annualizzazione volatilità (P2) + scaffold con `alloc` invece di `df_selected` (P3) + fix `Optional[float]` (P2/P4) — sono tre esempi concreti di bug intercettati via review cross-team prima del deploy. Materiale ricco per Sezione 7
- **Pattern architetturali da documentare nella Sezione architettura:** "validate at the boundary", "stub first wire later", "single source of truth per costanti condivise", "DB failure non blocca response"
- **Cross-team review process** documentabile: bug `BALANCED→MODERATE` segnalato in review P1→P2, fixato prima del wire — esempio diretto di "Process over Product"
- **Numerazione ADR e nomi label EN/IT:** entrambi esempi di come l'allineamento contratto tra team richiede esplicitazione formale (non basta "siamo tutti d'accordo")
- **Skeleton LaTeX in W2 invece di W4** (P4): gestione proattiva del rischio documentale — citabile in Lessons Learned
- **Distribuzione cluster SCF skewed (59% AGGRESSIVE)** (P3): da documentare onestamente in Limitations come US-centric bias + wealth oversampling, citando Grable & Lytton 1999 per il fatto che il MODERATE basso è coerente con letteratura comportamentale

---

## 11. Cosa NON è stato fatto in W2 e va recuperato

- ❌ `agent_pr.yml` (anche solo stub) — **rischio voto Criterio 5**
- ❌ `/compare`, `/advice`, `/backtest` endpoint (anche solo skeleton stub)
- ❌ API key header auth
- ❌ `test_data_loader.py` con dati yfinance reali
- ❌ ValidatedDataLoader full implementation (se ancora scaffold)
- ⚠ Numerazione ADR da riconciliare con dev plan
- ⚠ Inconsistenza `0.03`/`0.05` in `versione 2- smart single portfolio`

---

## 12. Quick-reference per ripartire in W3

**Files chiave toccati da P1 in W2:**
- `backend/api/main.py` (FastAPI app, `/profile` + `/optimize`)
- `backend/db/schema.sql` (EN UPPER labels)
- `backend/db/snapshots.py` (wired in `/optimize`)
- `tests/test_api.py` (9 test)
- `docs/adr/ADR-005-db-schema.md`
- `docs/adr/ADR-003-cloud-deploy.md`

**Files da toccare in W3:**
- `backend/api/main.py` (wire `/advice` + nuovi endpoint)
- `backend/data/loader.py` (ValidatedDataLoader full)
- `tests/test_data_loader.py` (nuovo)
- `.github/workflows/agent_pr.yml` (nuovo)
- `docs/adr/ADR-003-cloud-deploy.md` (finalizzare)

**Contratti interlocking attivi:**
- `ProfilerOutput` (P3 → P1 `/profile`)
- `OptimizationResult` (P2 → P1 `/optimize`)
- `NarratorResponse` (P4 → P1 `/advice`, W3)
- `DataQualityReport` (P1 → P2/P3, include `fallback_tickers_applied`)
