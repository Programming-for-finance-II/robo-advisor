# W3 — Memoria Consolidata (11 → 17 maggio 2026)
**Owner del documento:** P1 — Backend / Data Engineering (Sabrina)
**Periodo coperto:** Settimana 3 del piano (11 maggio – 17 maggio 2026)
**Scopo:** baseline di memoria per ripartire in W4 senza perdere contesto su decisioni, deliverable, dipendenze e criticità aperte. Documento composto a partire dai session log di P1 (12 mag s1 + s2), P2 (13–15 mag), P3 (17 mag) e P4 (13–14 mag).

---

## 1. Stato esecutivo a fine W3

W3 si chiude **in linea con il piano e con sblocco anticipato del Criterio 5**. P1 ha consegnato cinque milestone (`/advice` endpoint live, API key auth, `agent_pr.yml` operativo con PR #43 generata, `input_sanitiser.py`, ADR-003 merged). Tutti gli altri P hanno consegnato il loro deliverable W3:

- **P1**: `/advice` wire end-to-end (NarratorClient + 5-step validator + DB audit), API key header auth su tutti gli endpoint protetti, `agent_pr.yml` funzionante → **Criterio 5 sbloccato in W3** (anticipato rispetto a W4), `input_sanitiser.py` Layer 1, `ADR-003-cloud-deploy.md` merged
- **P2 (Emma)**: motore di backtest completo (3 scenari GFC/COVID/Rate Hike), `regime_detector.py` (correlazione + VIX, fallback ERC), `charts.py` con 4 funzioni Plotly, `ADR-006-regime-detector.md`
- **P3 (Matteo)**: Phase B classifier (HistGBM + SHAP + LR baseline) via Claude Code agentic workflow, 43 test passati, PR aperta in attesa di review P1
- **P4 (Elena)**: Chat Advisor wirato al pipeline LLM 3-stage, `docs/user_guide.md` (437 righe), `ADR-004-llm-narrator-validator.md`, 37/37 test validator + 11 cases EU Awareness Rule 9, AGENTS.md Evidence Log popolato

**93 test totali verdi su `main`** alla chiusura W3.

---

## 2. Cosa ho fatto io (P1) in W3

### Lunedì–Martedì 11–12 maggio (sessione 1, ~3–4 ore)
- **`/advice` endpoint live in `backend/api/main.py`** (branch `feature/p1-advice-endpoint`):
  - `AdviceRequest` / `AdviceResponse` Pydantic models
  - Recupero `recommendation` da DB per `recommendation_id`
  - Costruzione `GroundTruthPayload` tramite `get_mock_payload()` (scelta deliberata Phase A — da sostituire con dati reali in W4)
  - Chiamata `NarratorClient.narrate()` (P4)
  - **5-step `validate()`** (P4)
  - Aggiornamento DB audit trail (`validator_flags`, `system_prompt_hash`, `ground_truth_json_hash`)
  - Commento accademico inline che descrive le 3 stage della pipeline LLM
- **API key header auth (`X-API-Key`)** via `Depends(verify_api_key)` su `/profile`, `/optimize`, `/advice` — task aperto da W2 chiuso
- **`tests/test_advice_pipeline.py`** (branch `feature/p1-integration-tests`) — 4 integration test:
  - `test_advice_unknown_recommendation_id` → HTTP 404
  - `test_advice_happy_path` → 200 con risposta LLM validata
  - `test_advice_injection_blocked` → `injection_blocked=True`
  - `test_advice_response_schema` → tutti i campi presenti
- Merge conflict su `main.py` tra le due branch P1 → risolto via GitHub conflict resolver
- **Entrambe le PR mergiate in `main`** con CI verde → 93 test totali verdi
- ~6 fix commits per allineamento ruff (import order, variabili inutilizzate, indentazione, typo `rrec_id`)

### Martedì 12 maggio (sessione 2, ~2 ore)
- **`ANTHROPIC_API_KEY` configurata come secret** in GitHub Actions
- **Limite di spesa mensile $5** impostato su Anthropic Console (`robo-advisor-usi-2026` API key)
- **`.github/workflows/agent_pr.yml` scritto da zero** (era file vuoto):
  - Trigger: `workflow_dispatch` + push a `backend/optimizer/`
  - Legge tutti i file Python in `backend/optimizer/`
  - Chiama Claude API (`claude-sonnet-4-5`) per generare/migliorare docstring
  - Committa su branch `agent/optimizer-docstrings-{run_number}`
  - Apre PR via `gh pr create`
- Fix modello deprecato: `claude-sonnet-4-20250514` → `claude-sonnet-4-5`
- Risolto permessi PR: `GITHUB_TOKEN` non autorizzato in repo organizzazione privata → **PAT (Personal Access Token)** con scope `repo` + `workflow`, validità 90 giorni (scade ~agosto 2026 — copre la correzione del prof), aggiunto come secret `PAT_TOKEN`
- **Workflow triggerato con successo → PR #43 aperta automaticamente** da AI agent
  - URL: `https://github.com/Programming-for-finance-II/robo-advisor/pull/43`
  - **PR lasciata aperta intenzionalmente come evidence** per AGENTS.md (il merge non è richiesto dal Criterio 5)
- **`backend/llm/input_sanitiser.py` creato** — Layer 1 della pipeline di sicurezza LLM:
  - Limit 500 chars
  - Keyword blocking (14 pattern noti)
  - Wrap input utente in tag `<user_input>`
- **`sanitise()` wirato in `/advice`** come pre-call defence (prima di `NarratorClient`)
- **`docs/adr/ADR-003-cloud-deploy.md` scritto e merged**:
  - Streamlit Community Cloud vs Railway
  - Pro/contro motivati (costo, semplicità deploy, compatibilità SQLite)
  - Limitazioni SQLite documentate (no persistenza tra redeploy su Streamlit Cloud)
  - Railway come fallback documentato

---

## 3. Deliverable W3 di P1 vs piano (development_plan.pdf)

| Task pianificato W3 | Stato | Note |
|---|---|---|
| Wire `/advice` endpoint con `NarratorClient` + `validate()` | ✓ | PR `feature/p1-advice-endpoint` merged 12 mag |
| API key header auth (`X-API-Key`) | ✓ | Task aperto da W2, chiuso 12 mag — applicato a `/profile`, `/optimize`, `/advice` |
| Integration test suite | ✓ parziale | `test_advice_pipeline.py` (4 test). `test_data_loader.py` con yfinance reali da completare in W4 |
| `ADR-003-cloud-deploy.md` finalizzato e merged | ✓ | Merged 12 mag |
| `agent_pr.yml` operativo + PR #43 generata | ✓ | **Anticipato da W4 a W3** → de-rischio Criterio 5 totale |
| `input_sanitiser.py` Layer 1 | ✓ bonus | Non nel piano W3 — anticipato spontaneamente come hardening |
| ValidatedDataLoader full implementation (NaN gate, ffill, hash, UCITS fallback effettivo) | ▶ | Scaffold di W2 ancora attivo; da finalizzare W4 |
| `test_data_loader.py` con dati yfinance reali (≥1 anno) | ▶ | Pianificato in W4 |
| `/compare` endpoint | ✗ | Non implementato — slittato a W4 |
| `/backtest` endpoint wirato (`run_backtest()` ora disponibile da P2) | ✗ | P2 ha consegnato (PR #51 merged) → wire P1 da fare in W4 |
| Review PR `feature/p3-gbm-phase-b` di Matteo | ⏳ | Richiesta esplicita, da fare lunedì 18 mag |

---

## 4. Cosa hanno consegnato gli altri P in W3

### P2 — Emma (Quant/Optimizer)

**Backtest engine** (13 mag, PR #51 merged):
- `backend/optimizer/backtest.py`: loop giornaliero, rebalancing month-end, lookback 252gg, transaction cost `TC = (10 bps / 10000) × Σ|Δwᵢ|` deducato dal return del giorno di rebalancing
- Tre strategie in parallelo: HRP (chiama `optimize()`), MV (chiama `optimize_markowitz()`), 1/N (equal weight)
- Output: dataclass `ScenarioResult` serializzabile via `asdict()` → JSON (file per scenario + summary)
- `scripts/download_backtest_data.py`: prezzi yfinance per finestra `test_start − 252gg → test_end`, fallback UCITS→US se NaN ratio > 2%, ffill ≤5gg
- `tests/test_backtest.py`: 9 unit test deterministici (`np.random.default_rng(seed=42)`), no rete

**Regime detector** (14 mag, `feature/p2-regime-detector`):
- `backend/optimizer/regime_detector.py`: trigger primario `avg |ρ_LW| > 0.75`, trigger secondario VIX > 30, **logica OR (union)** → flag `regime`
- `get_erc_cluster_weights()`: fallback ERC cluster-level (equal weight per cluster → equal weight intra-cluster → clip + renormalise)
- Costanti locali `ASSET_WEIGHT_MIN = 0.05`, `ASSET_WEIGHT_MAX = 0.40` (debito tecnico: refactor a `universe_config` rimandato a W4)
- 3 test in `tests/test_optimizer.py`

**Plotly charts** (14 mag, `feature/p2-plotly-charts`):
- `backend/optimizer/charts.py`: 4 funzioni che restituiscono `go.Figure` pronte per `st.plotly_chart()`:
  - `plot_risk_contributions()` — bar chart orizzontale
  - `plot_dendrogram()` — dendrogram HRP da linkage matrix scipy
  - `plot_drawdown()` — drawdown chart per i 3 scenari (consuma JSON di backtest)
  - `plot_efficient_frontier()` — scatter frontier MV con marker HRP/MV
- Lazy import scipy/numpy dentro funzioni per evitare dipendenze top-level

**Bug fix bloccanti:**
- `ASSET_MIN` in `hrp.py`: `0.03` → `0.05` (allineamento con `universe_config.py` — debito tecnico da W1 risolto)

**Documentazione:**
- `docs/adr/ADR-006-regime-detector.md` (15 mag) — riflette esattamente l'implementazione: soglie 0.75 / VIX 30.0, logica OR, fallback ERC, riferimenti Longin & Solnik 2001, Maillard et al. 2010, Whaley 2009, López de Prado 2016

### P3 — Matteo (ML/Profiling)

**Phase B classifier completo** (17 mag, `feature/p3-gbm-phase-b`):
- `backend/ml/profiler/classifier.py`: **`HistGradientBoostingClassifier`** (non GBM classico) addestrato su SCF 2022 (n=4.595, implicate=1) con sample weights `WGT`
- **Motivazione tecnica:** `shap 0.50.0` ha rimosso supporto a `GradientBoostingClassifier` in `TreeExplainer` → migrazione a `HistGradientBoostingClassifier` (sklearn nativo, più veloce, SHAP compatibile). Fix autonomo di Claude Code documentato nel docstring.
- SHAP `TreeExplainer` per `top_drivers` normalizzati → passati al `ProfilerOutput` per il narratore LLM
- `LogisticRegression` come baseline di confronto

**Risultati training:**

| Metrica | HistGBM | LR Baseline |
|---|---|---|
| Train accuracy | 97.7% | 79.9% |
| CV 3-fold | **94.0% ± 0.15%** | 63.3% ± 2.9% |

→ Varianza CV ±0.15% indica robustezza, gap vs LR dimostra cattura di pattern non lineari

**`regime_detector.py` (scaffold P3):** stub che restituisce sempre `"normal"`, struttura pronta. **Nota: esiste ora un secondo `regime_detector.py` in P2 — chiarire la duplicazione (vedi criticità sezione 6).**

**Test profiler esteso:** 43 test passati, 2 skippati by design (aspettano `gbm_model.pkl`).

**Workflow agentic:** intero W3 P3 prodotto da Claude Code (lettura repo, scrittura codice, git add/commit/push, `gh pr create`) a partire da prompt strutturato. Documentato in `AGENTS.md`.

### P4 — Elena (Frontend/LLM/Docs)

**Risoluzione conflitti merge** (12 mag):
- PR #41 (`fix/advice-endpoint-integration` → main): 7 conflitti in `backend/api/main.py`, risolti accettando "incoming change" (main) per tutti
- Bug post-merge: classi `AdviceRequest` / `AdviceResponse` **duplicate** (causa: Claude Code aveva riscritto `main.py` in modo parzialmente diverso) → rimosse direttamente su GitHub editor → 93/93 test verdi
- **PR #41 chiusa senza merge** (codice già presente su main via PR #40 di P1)

**Chat Advisor UI** (13 mag):
- `render_chat()` in `frontend/app.py` wirato al pipeline LLM 3-stage: `get_mock_payload() → NarratorClient → validate() → display`
- Fix bug pagina bianca: rimosso `if __name__ == "__main__":`, sostituito con `main()` diretto (incompatibilità con runtime Streamlit)
- Fix `StreamlitSecretNotFoundError`: try/except graceful per `secrets.toml` mancante
- `.streamlit/secrets.toml` placeholder

**Documentazione:**
- `docs/adr/ADR-004-llm-narrator-validator.md` (13 mag): Narrator Pattern, pipeline 4 stadi, 9 regole system prompt, known limitations (false positive "safe/safe_haven", EU awareness keyword-based)
- 3 nuovi test EU Awareness Rule 9 (totale **11 cases**, 37/37 passed) in `TestEUAwarenessRule9`
- `docs/user_guide.md` (14 mag, 437 righe): flusso utente end-to-end, sezione EU Awareness, tabella limitazioni, API reference

**AGENTS.md Evidence Log popolato** con **PR #43 di P1** — log completo del prompt, modello (`claude-sonnet-4-5`), PR URL. **Criterio 5 ufficialmente coperto dalla documentazione.**

---

## 5. Stato dipendenze critiche (mappa P1-centric)

### IN INGRESSO su P1

| Da | Cosa | Atteso entro | Stato |
|---|---|---|---|
| P3 | `rule_based.py` | Lun W2 | ✓ consegnato W1 |
| P3 | GBM Phase B per `/profile` Phase B | W3 | ✓ consegnato 17 mag (PR `feature/p3-gbm-phase-b` in review) — **richiesta review P1** |
| P2 | `optimize()` callable | Mar W2 | ✓ consegnato |
| P2 | `run_backtest()` + `ScenarioResult` JSON schema | W3 | ✓ consegnato 13 mag (PR #51 merged) |
| P2 | `regime_detector.py` per Stress Banner | W3 (atteso giov per P4) | ✓ consegnato 14 mag |
| P2 | `charts.py` Plotly | W3 | ✓ consegnato 14 mag |
| P4 | `validator.py` per wire `/advice` | W3 | ✓ consegnato 9 mag (W2) |
| P4 | `NarratorClient` | W3 | ✓ consegnato |

### IN USCITA da P1

| A | Cosa | Stato |
|---|---|---|
| P4 | `/profile` + `/optimize` + `/advice` endpoint live | ✓ tutti disponibili |
| P4, P3 | API key auth + URL deploy | ⏳ deploy W4 |
| P3 | review PR `feature/p3-gbm-phase-b` | ⏳ **dovuta da P1 lunedì 18 mag** |
| Team | `agent_pr.yml` + PR #43 URL per AGENTS.md evidence | ✓ **Criterio 5 coperto, comunicato a Elena** |
| P2 | `/backtest` endpoint wirato che consuma `run_backtest()` | ✗ da fare W4 |
| Team | `/compare` endpoint | ✗ da fare W4 |

---

## 6. Criticità aperte da gestire in W4

### 🔴 Alta priorità

1. **Numerazione ADR caotica** — situazione attuale nel repo:
   - `ADR-001-hrp-over-markowitz.md` (P4, W1)
   - `ADR-002-scf-preprocessing.md` (P3, W1)
   - `ADR-003-cloud-deploy.md` (P1, W3, **merged**)
   - `ADR-004-llm-narrator-validator.md` (P4, W3, merged)
   - `ADR-005-db-schema.md` (P1, W1/W2) — **nel piano sarebbe ADR-001**
   - `ADR-006-regime-detector.md` (P2, W3, merged)
   - Ancora da scrivere: `ADR-004-ledoit-wolf-shrinkage.md` (P2 — **collisione con ADR-004 P4**), `ADR-005-scf-implicate-choice.md` (P3 — **collisione con ADR-005 P1**)

   → **Azione W4 (P4 owner LaTeX):** riunione di riconciliazione finale. P2 e P3 devono usare numeri liberi nel repo (007, 008). I riferimenti nel PDF devono usare i numeri reali nel repo, non quelli del piano.

2. **Due `regime_detector.py` nel repo:**
   - `backend/optimizer/regime_detector.py` (P2, **completo**: correlazione + VIX, fallback ERC)
   - `backend/ml/profiler/regime_detector.py` (P3, **scaffold** che restituisce sempre `"normal"`)
   - Sono lo stesso modulo o due moduli distinti? Se uno solo, consolidare al P2. Se distinti, chiarire i ruoli (es. ML usa regime detector dell'optimizer come dependency).
   - **Azione W4 (P1):** verifica nel primo standup, propone consolidamento sul modulo P2.

3. **Deploy in W4 = dipendenza forte verso P4** (chat page test):
   - Streamlit Community Cloud + SQLite persisted volume è la rotta documentata in ADR-003
   - Railway come fallback
   - `ANTHROPIC_API_KEY` + `PAT_TOKEN` da configurare come secrets sul provider scelto
   - **Alert permanente:** se entro giovedì W4 il deploy non è sotto controllo, alzare l'allarme

4. **`/compare` e `/backtest` endpoint ancora mancanti** — task slittati da W3.
   - `/backtest` può essere wirato direttamente perché `run_backtest()` è disponibile (PR #51 merged)
   - `/compare` richiede confronto HRP vs MV vs 1/N — può consumare l'output di `run_backtest()` o calcolare on-the-fly

### 🟡 Media priorità

5. **PR #43 ha merge conflict su `hrp.py`** (file P2). Per il Criterio 5 l'URL è sufficiente, ma per pulizia W4 sarebbe ideale risolverlo o documentare che è intenzionale.

6. **Costanti locali in `regime_detector.py` (P2)** — `ASSET_WEIGHT_MIN`/`MAX` duplicati invece di importare da `universe_config`. Refactor da fare in W4 per single source of truth completa.

7. **`ValidatedDataLoader` full implementation** non confermato — verificare in W4 che NaN gate, hash, UCITS fallback effettivo siano tutti implementati e testati (non solo scaffold).

8. **`test_ucits_fallback.py`** (W4, shared con P3) — ≥3 test cases: triggers su DataFrame vuoto, `fallback_tickers_applied` popolato in `DataQualityReport`, DB row registra il fallback.

### 🟢 Bassa priorità / monitoraggio

9. **`gbm_model.pkl` statico** (P3): il modello è trained offline su SCF 2022, non viene riaddestrato a runtime. Da menzionare in Limitations.

10. **VIX trigger nel regime detector è scaffold:** in produzione richiederebbe un feed VIX real-time separato. Da menzionare in Limitations.

---

## 7. Pattern architetturali / decisioni rilevanti emerse in W3

| Pattern / Decisione | Owner | Perché conta | PDF |
|---|---|---|---|
| **Pipeline LLM 3-stage**: `input_sanitiser` (Layer 1) → `NarratorClient` (Layer 2) → `validator` (Layer 3) | P1 + P4 | Separation of concerns sicurezza LLM — defence-in-depth | Sezione 4 LLM Narrator |
| **`_PROFILE_LABEL_MAP`** (adapter MODERATE→balanced) | P1 | Mappa dominio DB (UPPER) vs dominio LLM payload (lower) — separation of concerns | Sezione architettura |
| **Mock at the boundary** (test mockano `init_db`, `anthropic.Anthropic`, env var — non il codice interno) | P1 | "Test the contract, not the implementation" | Sezione testing / Lessons Learned |
| **PRAGMA foreign_keys = OFF** in test setup | P1 | Limitazione consapevole dell'approccio SQLite in contesti di test | Limitations |
| **PAT_TOKEN workaround** per `agent_pr.yml` | P1 | Restrizioni GitHub di organizzazioni private non permettono `GITHUB_TOKEN` per aprire PR. Soluzione: PAT con scope limitato | Lessons Learned / Infrastructure |
| **Doppio trigger regime (correlazione OR VIX)** | P2 | Più robusto di un singolo segnale, asimmetria costo FP/FN | Sezione 3 Portfolio Optimization |
| **HistGBM over GBM classico** | P3 | Forzato da deprecazione SHAP, ma anche più veloce e sklearn nativo | Sezione 2 ML Profiler |
| **SHAP `top_drivers` normalizzati** per LLM | P3 | Il narratore può commentare ragioni della classificazione senza inventare correlazioni — punto di differenziazione | Sezione 2 ML Profiler |
| **Pattern lazy import** (scipy/numpy dentro funzioni) | P2 | Evita dipendenze top-level non necessarie | Coding style |
| **`temperature=0.0`** nel narrator | P4 | Output deterministico e auditabile | Sezione 4 LLM Narrator |
| **CI-driven development**: 6 fix commits ruff in una sessione P1, 4 round P2 | tutti | Esempio concreto di feedback loop CI → fix → commit → CI | Lessons Learned |
| **Flusso agentic completo** (Claude Code in W3 P3) | P3 | Intero W3 P3 prodotto da AI agent a partire da prompt strutturato | Lessons Learned |

---

## 8. PR e CI a chiusura W3

Stato visto nei log:
- `feature/p1-advice-endpoint` — `/advice` wire + API key auth → **merged** in main (PR #40)
- `feature/p1-integration-tests` — 4 test `test_advice_pipeline.py` → **merged** in main
- `fix/advice-endpoint-integration` (P4) — PR #41 → **chiusa senza merge** (codice già su main, conflitti risolti dopo)
- `agent/optimizer-docstrings-{N}` — **PR #43 aperta da AI agent** → **lasciata aperta come evidence** (merge conflict su hrp.py, irrilevante per Criterio 5)
- `feature/p2-backtest-scenarios` — Emma, motore backtest + 9 test → **merged** in main (PR #51)
- `feature/p2-regime-detector` — Emma, regime + 3 test → CI verde, in attesa di review/merge
- `feature/p2-plotly-charts` — Emma, 4 funzioni Plotly → CI verde, in attesa di review/merge (urgente, P4 ne ha bisogno lunedì)
- `feature/p2-docs-adrs` — Emma, ADR-006-regime-detector → committato
- `feature/p3-gbm-phase-b` — Matteo, classifier + scaffold regime + AGENTS.md update → CI verde, **in attesa di review P1**
- `feature/p4-chat-advisor-ui` — Elena, EU awareness validator tests → PR aperta
- `feature/p4-docs` — Elena, user_guide.md → **merged** in main
- `AGENTS.md` Evidence Log con PR #43 → committato direttamente su main da Elena

⚠ **Azioni P1 lunedì 18 mag (inizio W4):**
1. Review PR `feature/p3-gbm-phase-b` di Matteo (richiesta esplicita)
2. Review e merge PR P2 (`feature/p2-regime-detector`, `feature/p2-plotly-charts`) — sblocca P4 per `render_portfolio()` con dati reali

---

## 9. Piano W4 (18–24 maggio) — vista P1

Dal dev plan + criticità accumulate:

**Mon–Tue (18–19 mag):**
- Review PR P3 `feature/p3-gbm-phase-b` e PR P2 (regime + charts) — sblocca team
- Configurare deploy Streamlit Community Cloud + SQLite persisted volume:
  - Connettere repo GitHub
  - Configurare secrets (`ANTHROPIC_API_KEY`, `PAT_TOKEN`)
  - Verificare path SQLite per persistenza
- Aggiornare `README.md` con istruzioni deploy
- Verificare consolidamento `regime_detector.py` (P2 vs P3) — proporre fix nel daily

**Wed–Thu (20–21 mag):**
- `tests/test_ucits_fallback.py` con ≥3 test cases (shared con P3):
  - Fallback triggers quando UCITS ticker → DataFrame vuoto
  - `fallback_tickers_applied` popolato in `DataQualityReport`
  - DB row registra il fallback
- `docker-compose.yml` per local dev (SQLite volume + hot reload + .env support)
- Full pytest suite con `pytest --cov` → target **≥80% line coverage**
- Wire `/backtest` endpoint che consuma `run_backtest()` di P2
- Wire `/compare` endpoint (HRP vs MV vs 1/N)
- Completare `ValidatedDataLoader` full (se ancora scaffold)
- `test_data_loader.py` con dati yfinance reali (≥1 anno history)

**Fri (22 mag):**
- Verifica `agent_pr.yml` ancora operativo (PR #43 esiste già, ma il workflow deve restare verde)
- Allineare con P4 per finalizzare `README.md`:
  - Installazione con `uv`
  - `docker-compose up` reference
  - Usage examples con sample output
  - API documentation per tutti gli endpoint
  - User guide section (requisito esplicito del prof — `docs/user_guide.md` già pronto da P4)
- DB hardening finale — `validator_flags`, `retry_count`, `fallback_triggered` loggati correttamente

**Sat–Sun (23–24 mag):**
- End-to-end manual test della app deployata
- Git tag `v1.0` + GitHub Release con changelog
- Partecipazione a review release v1.0 con il team
- Submission iCorsi

---

## 10. Note per il PDF accademico (raccolte da W3)

- **Pipeline LLM 3-stage (sezione 4):** `input_sanitiser.py` (Layer 1, 14 keyword + 500 char limit + wrap `<user_input>`) → `NarratorClient` (Layer 2, `temperature=0.0`) → `validate()` (Layer 3, 5 step). Defence-in-depth contro prompt injection.
- **Criterio 5 evidence:** PR #43 aperta automaticamente da `agent_pr.yml` (GitHub Actions) chiamando Claude API (`claude-sonnet-4-5`) per generare docstring optimizer. URL: `https://github.com/Programming-for-finance-II/robo-advisor/pull/43`. Citabile come esempio concreto di agentic workflow.
- **PAT workaround (Lessons Learned):** restrizioni GitHub organizzazione privata non permettono `GITHUB_TOKEN` per aprire PR → Personal Access Token con scope `repo` + `workflow` come soluzione. Documenta una limitazione reale dell'ambiente CI/CD in contesti accademici/organizzativi.
- **ADR-003 (Sezione 6 Limitations):** SQLite non persiste tra redeploy su Streamlit Cloud — scelta accettata per il prototipo universitario, motivata da semplicità deploy + costo zero. Railway documentato come fallback.
- **Risultati ML (Sezione 2):** HistGBM 94.0% ± 0.15% CV vs LR 63.3% ± 2.9%. Gap >30pp dimostra cattura pattern non lineari (Guiso et al. 2018). Varianza ±0.15% indica robustezza/non memorizzazione.
- **Backtest (Sezione 5):** 3 scenari (GFC 2008, COVID 2020, Rate Hike 2022). HRP dovrebbe mostrare vantaggio su MV in GFC/COVID grazie a robustezza covarianza Ledoit-Wolf. 1/N benchmark naïve di DeMiguel et al. (2009).
- **Limitazioni da citare onestamente:**
  - Transaction cost model semplificato (10 bps su turnover one-way, no bid-ask, no impact)
  - Pesi tra rebalancing tenuti costanti (no deriva) → turnover reale > modello
  - CSPX.L e AGGH.MI non esistevano nel 2008 → fallback SPY/AGG (economicamente equivalente, non UCITS)
  - VIX trigger scaffold (no feed real-time)
  - `gbm_model.pkl` statico, non riaddestrato a runtime
  - False positive "safe/safe_haven" nel validator (keyword-based EU awareness)
- **Bug history (Lessons Learned):**
  - Doppia annualizzazione volatilità (P2, W2) — bug Ledoit-Wolf intercettato in review
  - Classi duplicate post-merge in `main.py` (P1+P4, W3) — non rilevato dal conflict resolver, intercettato da CI rosso
  - "investors" come substring di "invest" bloccato dal validator → "European allocations" — esempio di tuning iterativo regole di sicurezza
  - Claude Code aveva riscritto `main.py` parzialmente diverso dal design → riallineamento manuale necessario
  - `if __name__ == "__main__":` incompatibile con runtime Streamlit (P4)
  - Modello `claude-sonnet-4-20250514` deprecato → aggiornato a `claude-sonnet-4-5`
- **Flusso agentic concreto:** intero W3 P3 prodotto da Claude Code a partire da prompt strutturato; PR #43 di P1 generata da GitHub Actions + Claude API. Due esempi di "Process over Product" che danno materiale ricco alla sezione Lessons Learned.
- **CI-driven development:** ~6 fix commits ruff in una singola sessione P1, 4 round P2 — esempio concreto di feedback loop CI → fix → CI verde.

---

## 11. Cosa NON è stato fatto in W3 e va recuperato in W4

- ❌ `/compare` endpoint (slittato da W2 a W3 a W4)
- ❌ `/backtest` endpoint wire (ora possibile, `run_backtest()` disponibile)
- ❌ `ValidatedDataLoader` full implementation (NaN gate, ffill, hash, UCITS fallback effettivo non solo scaffold) — verificare e completare
- ❌ `test_data_loader.py` con dati yfinance reali (≥1 anno history)
- ❌ `test_ucits_fallback.py` (≥3 cases, shared con P3)
- ❌ `docker-compose.yml` per riproducibilità locale
- ❌ Cloud deploy live
- ❌ pytest coverage ≥80% verificata via `pytest --cov`
- ❌ Review PR `feature/p3-gbm-phase-b` — **urgente lunedì 18 mag**
- ⚠ Numerazione ADR da riconciliare (doppia collisione: ADR-004 P2 vs P4, ADR-005 P3 vs P1)
- ⚠ Consolidamento doppio `regime_detector.py` (P2 vs P3)

---

## 12. Quick-reference per ripartire in W4

**Files chiave toccati da P1 in W3:**
- `backend/api/main.py` (`/advice` endpoint, API key auth, integrazione `input_sanitiser`)
- `backend/llm/input_sanitiser.py` (nuovo)
- `tests/test_advice_pipeline.py` (nuovo, 4 test)
- `.github/workflows/agent_pr.yml` (nuovo, operativo)
- `docs/adr/ADR-003-cloud-deploy.md` (merged)

**Files da toccare in W4:**
- `backend/api/main.py` (wire `/compare`, `/backtest`)
- `backend/data/loader.py` (ValidatedDataLoader full, se ancora scaffold)
- `tests/test_data_loader.py` (con yfinance reali)
- `tests/test_ucits_fallback.py` (nuovo)
- `docker-compose.yml` (nuovo)
- `README.md` (finalizzare con installazione, API docs, user guide section)
- `.streamlit/config.toml` / Streamlit Cloud secrets (deploy)

**Secrets in uso:**
- `ANTHROPIC_API_KEY` — GitHub Actions secret, $5 monthly cap
- `PAT_TOKEN` — Personal Access Token, scope `repo` + `workflow`, scade ~agosto 2026

**Workflow GitHub Actions attivi:**
- `ci.yml` — lint + pytest su push/PR
- `agent_pr.yml` — `workflow_dispatch` + push a `backend/optimizer/` → genera/aggiorna docstring via Claude API → PR automatica

**Endpoint API live a fine W3:**
- `POST /profile` ✓ (rule_based.py di P3, Phase A)
- `POST /optimize` ✓ (HRP di P2 + ValidatedDataLoader + DB audit)
- `POST /advice` ✓ (input_sanitiser → NarratorClient → validate → DB audit)
- `POST /compare` ✗ da fare W4
- `POST /backtest` ✗ da fare W4 (dipendenza P2 risolta)

**Contratti interlocking attivi a fine W3:**
- `ProfilerOutput` (P3 → P1 `/profile`)
- `OptimizationResult` (P2 → P1 `/optimize`)
- `NarratorResponse` (P4 → P1 `/advice`) — wirato
- `DataQualityReport` (P1 → P2/P3, include `fallback_tickers_applied`)
- `ScenarioResult` (P2 → P1 `/backtest` da wirare W4)
- `GroundTruthPayload` via `get_mock_payload()` (P4 mock → P1 `/advice`, da sostituire con dati reali W4)

**Numerazione ADR reale nel repo (da non confondere con il piano):**

| File ADR nel repo | Owner | Stato | Settimana |
|---|---|---|---|
| ADR-001-hrp-over-markowitz.md | P4 | merged | W1 |
| ADR-002-scf-preprocessing.md | P3 | merged | W1 |
| ADR-003-cloud-deploy.md | **P1** | **merged W3** | W3 |
| ADR-004-llm-narrator-validator.md | P4 | merged | W3 |
| ADR-005-db-schema.md | P1 | merged | W1/W2 |
| ADR-006-regime-detector.md | P2 | committato | W3 |
| ADR-007 disponibile per Ledoit-Wolf (P2 W4) | — | — | — |
| ADR-008 disponibile per SCF implicate choice (P3 W4) | — | — | — |

---

*Fine documento W3 — Buon W4!*
