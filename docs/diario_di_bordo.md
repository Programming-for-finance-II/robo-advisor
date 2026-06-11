# Project Diary (Diario di Bordo)

Consolidated session logs, ordered by date and grouped by day, then by role (P1, P2, P3, P4) within each day.

## Team

- **P1 — Sabrina** — Backend / Data Engineering
- **P2 — Emma** — Quant / Portfolio Optimization
- **P3 — Matteo** — ML / Risk Profiling
- **P4 — Elena** — Frontend / LLM / Docs

---

# 27 April 2026 — Week 1

## P3 — ML / Risk Profiling
**Estimated duration:** 1h30

### What I did

- Defined the complete questionnaire structure: 10 questions split into 3 sections (Who You Are Financially, How You Invest, How You React)
- Discussed and chose the Grable & Lytton (1999) methodology as the academic basis for the questions
- Defined the scoring system (0–30) with confidence zones and an override rule for Q7
- Produced the file `docs/questionnaire_schema.md` with questions, answer options, rationale for each question, and bibliographic references
- Configured Git locally, cloned the repo, created the branch `feature/p3-questionnaire-schema`
- Pushed the file to GitHub and opened PR #1 toward main

### How I did it

- Designed the questionnaire structure and chose the methodology myself
- Discussed each question and its mapping to the three profiles (CONSERVATIVE, MODERATE, AGGRESSIVE)
- Ran the Git commands from the terminal (Mac) for clone, branch, add, commit, push
- Opened the PR manually on GitHub

### Difficulties

- Initial error with `git add` because the file was not yet in the `docs/` folder — solved by copying the file from Downloads with `cp`
- Initial understanding of the Git flow (branch, PR, main) — clarified during the session

### Achievements / Key decisions

- **Questionnaire completed and committed** — first P3 deliverable on GitHub ✅
- **PR #1 opened** on `feature/p3-questionnaire-schema` → main
- Key decision: Q7 has an override rule — if the user answers "safety net", the profile is capped at CONSERVATIVE regardless of the total score
- Key decision: Q9 placed last to reduce social desirability bias — academically defensible
- Confidence zones defined: borderline at 8–9, 10–11, 18–19, 20–21 → `low_confidence_flag = True`

### Next steps

- Wait for P1's (emmaerba) review on PR #1
- Start `backend/ml/profiler/rule_based.py` (Wed–Thu W1 task)
  - Implement scoring logic from the questionnaire
  - Handle Q7 override rule
  - Output: `profile_label` + `confidence` + `low_confidence_flag`
- Verify that `AGENTS.md` has been pushed by P4

### Notes for the academic PDF

- The questionnaire follows the **Grable & Lytton (1999) Risk Tolerance Scale** — citation ready
- The behavioral questions (Q8, Q9) use first-person framing to reduce social desirability bias — defensible motivation
- Q6 + Q5 together identify asymmetric profiles (those who know but have never invested, or vice versa) — interesting point to mention in the ML Risk Profiler section
- Bibliographic references already prepared in the file: Grable & Lytton 1999, Guiso et al. 2018, Fed Reserve SCF 2022, MiFID II Art. 25

---

# 28 April 2026 — Week 1

## P1 — Backend / Data Engineering
**Plan:** W1 Foundation (27 Apr – 3 May)

### What I did

- Configured `ci.yml` in `.github/workflows/` — GitHub Actions with lint (ruff) + pytest on every push and PR
- Solved the CI error "collected 0 items" by adding `tests/test_placeholder.py`
- Solved the CI error "E501 line too long" by setting `line-length = 100` in `pyproject.toml`
- Reviewed and approved emmaerba's PR #2 (`universe_config.py`): corrected `ASSET_WEIGHT_MIN` from `0.03` to `0.05` for alignment with design v3.1
- Merged PR #2 (universe_config.py) and PR #3 (ci.yml) into `main`
- Created `backend/data/schema.sql` — DB schema v3.1 with tables `users`, `recommendations`, `market_data_snapshots` and their indexes
- Created `backend/data/loader.py` — complete `ValidatedDataLoader` with NaN gate, ffill, SHA-256 hash, UCITS fallback logic, `DataQualityReport`
- Configured branch protection on `main`: require PR + 1 review + green CI before merge

### How I did it

- All the work was done directly on GitHub (web interface) without using local git
- CI configured with `astral-sh/setup-uv@v5` for dependency management via `uv`
- Reviewed emmaerba's code by comparing it against the canonical design v3.1 before approving the merge
- `ValidatedDataLoader` written following design v3.1: `load()` interface returning `(pd.DataFrame, DataQualityReport)`, fallback ticker resolved before the main download, SHA-256 hash computed on `prices.to_csv()`
- Branch protection configured via Settings → Branches → Add ruleset

### Difficulties

- CI failed with exit code 5 (zero tests found) — solved by adding `test_placeholder.py`
- CI failed with E501 (line too long in the ETF rationales) — solved by raising `line-length` to 100
- GitHub navigation not immediate for someone without experience on the platform (branch switching, committing to a specific branch)
- `loader.py` already existed as an empty file (placeholder from the initial commit) — modified instead of recreated

### Achievements / Key decisions

- **W1 completed at 85%** in a single session
- **Green CI** on `main` — every future PR will have automatic feedback
- **Branch protection active** — a professional process visible in the repo history
- **`universe_config.py` aligned with design v3.1** — `ASSET_WEIGHT_MIN = 0.05`, 8 ETFs, 4 clusters, 3 UCITS tickers, integrity assertions at import-time
- **DB schema v3.1 complete** with all required fields: `ucits_tickers_used`, `fallback_tickers_applied`, `regulatory_context`, `etf_universe_version`, `market_data_hash`
- **`ValidatedDataLoader` scaffold** ready — complete interface, UCITS fallback logic implemented, `DataQualityReport` with a `to_dict()` method for DB serialization

### Next steps

- **`snapshots.py`** — `market_data_snapshots` logic for audit trail (Fri W1)
- **`test_data_loader.py`** — at least 2 happy-path tests (Fri W1)
- **FastAPI skeleton** — 5 endpoint stubs `/profile`, `/optimize`, `/compare`, `/advice`, `/backtest` (start of W2)
- **Rate limiting** with `slowapi` + API key header auth (W2)
- **ADR-001** — SQLite vs PostgreSQL document (W2)
- Verify that P3 delivers an importable `rule_based.py` by Monday W2 — if not available, prepare a 3-cluster stub

### Notes for the academic PDF

- The choice of `uv` as package manager can be justified in the PDF as a modern, reproducible choice compared to classic `pip` — installation speed and deterministic lockfile
- Branch protection with mandatory CI is an element of the agentic process documentable in the "Lessons Learned" section (Section 7)
- The `market_data_hash` field (SHA-256 of `prices.to_csv()`) deserves a note in the DB section: it guarantees bit-for-bit reproducibility of recommendations even if yfinance retroactively adjusts historical data (splits, dividends)
- The UCITS/US tension in `universe_config.py` (EFA, GLD, VNQ without a liquid UCITS equivalent) is direct material for the "Limitations and Failure Modes" section

---

## P2 — Quant / Portfolio Optimization (session 1)
**Estimated duration:** ~1.5 hours

### What I did

- Verified the state of the shared repo: the `backend/data/` structure was already initialized by P1, `universe_config.py` present but empty
- Cloned the repo locally (`git clone`)
- Created the branch `feature/p2-universe-config`
- Pasted and committed the `universe_config.py` code on GitHub (first via browser, then synced locally)
- Ran the import test from the terminal (`get_primary_tickers()`)
- Opened Pull Request #2 toward `main` with a review request to P1 (Sabrina15072002)

### How I did it

- Code written, aligned with the canonical design v3.1
- File structured with `dataclass(frozen=True)` for immutability of the configuration
- Helper functions implemented for direct compatibility with `ValidatedDataLoader` (P1) and `hrp.py` (P2 W2)
- Integrity assertions run at import-time (`_validate_universe()`) to protect against accidental misconfiguration
- Git workflow: clone → branch → commit on GitHub browser → pull locally → test → PR

### Difficulties

- First experience with Git and GitHub: browser vs terminal flow not clear initially
- Commit on GitHub via browser not saved the first time (missed clicking "Commit changes")
- `cd robo-advisor` run twice by mistake (already inside the folder after the clone)
- `git pull origin main` did not download the file because the commit was on a separate branch — solved with `git pull origin feature/p2-universe-config`

### Achievements / Key decisions

- **W1 task #1 completed:** `universe_config.py` written, tested, PR opened
- **P1 dependency unblocked:** P1 can now implement `ValidatedDataLoader` with fallback logic
- **Design choice:** `EFA` keeps the same ticker as both primary and fallback (no UCITS equivalent with adequate yfinance coverage) — documented in the `rationale` field
- **Design choice:** `XEON.MI` as EUR cash instead of `BIL` USD — more consistent for an EU investor, with `BIL` fallback if yfinance returns excessive NaNs
- **Design choice:** `AGGH.MI` as EUR-hedged aggregate bond instead of `AGG` USD — reduces FX risk for an EU investor, cluster `safe_haven`
- Import-time assertions verify: exactly 8 ETFs, no duplicates, 4 clusters present, ≥3 UCITS

### Next steps

- W1 task #2: scaffold `backend/optimizer/hrp.py` with `OptimizationResult` TypedDict/dataclass
- W1 task #3: stub `tests/test_optimizer.py` with at least 2-3 structural tests
- Start Ledoit-Wolf with `pypfopt.CovarianceShrinkage` on synthetic data
- Wait for the merge of P1's PR before proceeding with the import of `universe_config` in `hrp.py`

### Notes for the academic PDF

- **Hybrid UCITS/US universe:** the choice to keep a UCITS primary and a US fallback is motivated by MiFID II compliance for EU investors. To be cited in Section 3 (Portfolio Optimization) as a deliberate design choice, not a technical one.
- **AGGH.MI vs AGG:** the substitution introduces slightly reduced correlation with TLT (different denomination currency) — the HRP dendrogram will reflect this difference in the structure of cluster C. Expected and didactically relevant result.
- **Cluster D (cash):** minimum allocation guaranteed in all profiles via `ASSET_WEIGHT_MIN = 0.03` — ensures a liquidity buffer. To be mentioned as a risk management choice in the guardrail section.
- Limitation to cite: `EFA` has no UCITS equivalent with comparable liquidity and data coverage on yfinance — geographic gap in the chosen ETF universe.

---

## P2 — Quant / Portfolio Optimization (session 2)
**Estimated duration:** ~30 minutes

### What I did

- Generated and pasted the `OptimizationResult` TypedDict into `backend/optimizer/hrp.py`
- Verified the import from the terminal with `python3 -c "from backend.optimizer.hrp import OptimizationResult; print('OK')"` → OK
- Opened PR #4 toward `main` from the branch `feature/p2-optimizer-scaffold`
- Requested a review from Sabrina15072002 (P1)
- Fixed a ruff lint error in `hrp.py` (unordered imports)
- Fixed a ruff lint error in `backend/data/loader.py` (unused `Optional` import — P1's file)
- Green CI: "All checks have passed" ✅

### How I did it

- `OptimizationResult` code written, aligned with the canonical design v3.1
- Structure: `TypedDict` with `Literal` for enum-like fields (`algorithm`, `solver_status`)
- File created directly from the GitHub browser (online editor) to avoid local branch issues
- Lint fix also done from the GitHub browser editor
- Import verification done from the local terminal after `git pull origin feature/p2-optimizer-scaffold`

### Difficulties

- **VS Code was not saving the file** — Cmd+S produced no visible effect, the "M" (modified) marker stayed on the tab. Solved by bypassing VS Code and editing the file directly from the GitHub browser.
- **The `code` command was not available in the terminal** — `zsh: command not found: code`. The VS Code shell command was not installed. Worked around with the browser editor.
- **Local branch not aligned with the remote** — `git push` failed with "src refspec does not match any" because the branch had been created first on the GitHub browser and did not exist locally. Solved with `git checkout -b feature/p2-optimizer-scaffold` + `git pull`.
- **CI failed due to an error in P1's file** — `backend/data/loader.py` had an unused `from typing import Optional`. Fixed directly on the `feature/p2-optimizer-scaffold` branch with a commit from the browser.

### Achievements / Key decisions

- **W1 task #2 completed:** `OptimizationResult` TypedDict written, verified, PR #4 opened with green CI
- **Fields included:** `algorithm`, `weights`, `expected_return`, `expected_volatility`, `sharpe_ratio`, `risk_contributions`, `optimizer_version`, `solver_status`, `ucits_tickers_used`, `fallback_tickers_applied`
- The `ucits_tickers_used` and `fallback_tickers_applied` fields are v3.1 additions — needed for audit trail and UI
- The `risk_contributions` field is a P0 requirement: it is consumed by the LLM narrator (P4) and by the validator

### Next steps

- W1 task #3: stub `tests/test_optimizer.py` with at least 2-3 structural tests
- Wait for the merge of PR #4 by Sabrina (P1) before proceeding with the import of `OptimizationResult` in other modules
- Install the VS Code command line tools (`Shell Command: Install 'code' command in PATH`) to avoid future problems

### Notes for the academic PDF

- `OptimizationResult` as an interface contract is a defensible design choice: it guarantees that all modules (P1, P3, P4) receive structured, typed data, reducing integration errors
- The `risk_contributions` field deserves mention in the Portfolio Optimization section: it is the direct link between the optimizer and the XAI/LLM layer
- The UCITS fields are motivated by MiFID II compliance — citable in the EU Investor Note section

---

## P3 — ML / Risk Profiling
**Estimated duration:** ~2.5 hours

### What I did

- Reviewed the complete W1 tasks and identified the progress status
- Decided the canonical naming for `profile_label`: **CONSERVATIVE / MODERATE / AGGRESSIVE** (EN, UPPER) — to propagate to the entire codebase
- Wrote the complete `backend/ml/profiler/rule_based.py` (Phase A profiler)
- Applied two fixes from an external code review:
  - Fix #1: "at the boundary" validation — extracted a private `_compute_score_unchecked` to avoid double validation in the `profile_user → compute_score` path
  - Fix #2: normalization of `top_drivers` against the maximum **possible** deviation (constant 1.5) instead of the observed one — avoids inflated importance on uniformly lukewarm responses
- Ran a smoke test on all 14 boundaries of the scoring table + Q7 override + all-equal responses case
- Committed on the branch `feature/p3-rule-based-profiler` and pushed to GitHub
- Opened PR #6 on GitHub toward `main`
- Identified a naming conflict in P1's `schema.sql` (IT vs EN)
- Left a comment on PR #6 notifying P1 (@emmaerba) of the conflict

### How I did it

- Code written starting from the already existing `questionnaire_schema.md` v1.0 schema
- Approach: rigorous type hints, named constants (zero magic numbers), NumPy-style docstrings, pure functions with no side effects
- Fixes identified through an external code review and critically evaluated before applying
- Smoke test run directly in Python before the commit
- Git operations run from the macOS terminal (`zsh`)
- PR opened manually in the GitHub browser

### Difficulties

- Terminal initially opened in the home `~` instead of the repo folder — solved with `cd ~/robo-advisor`
- `compare/base` branches swapped in the GitHub UI on the first attempt — fixed manually
- `profile_label` naming conflict discovered while reading P1's `schema.sql` (IT vs EN) — flagged in the PR, awaiting fix from P1

### Achievements / Key decisions

- **`rule_based.py` complete and committed** — PR #6 opened, awaiting P1 review
- **Canonical naming fixed**: `CONSERVATIVE / MODERATE / AGGRESSIVE` (EN, UPPER) — decision to propagate to P1 (`schema.sql`) and P4 (Ground Truth JSON)
- **Stable `ProfilerOutput` schema**: identical to what the GBM will produce in W3, no downstream refactor needed
- **Q7 override documented as a hard MiFID II rule** (confidence = 1.0, not probabilistic) — an academically relevant distinction for the PDF
- **`top_drivers` Phase A**: deterministic heuristic documented, schema identical to SHAP Phase B

### Next steps

- Wait for P1's review/merge on PR #6 (must fix the `schema.sql` naming IT→EN)
- Create the `backend/ml/profiler/scf_pipeline.py` scaffold (W1 priority, to do)
- Create the `docs/adr/ADR-002-scf-preprocessing.md` draft (W1 priority, by Sunday)
- W2: write `tests/test_profiler.py` with ≥3 tests per label + already identified edge cases

**Edge cases to cover in `test_profiler.py` (W2):**
- score 7 vs 8 (boundary CONS high → CONS borderline)
- score 9 vs 10 (boundary CONS → MOD)
- score 17 vs 18 (boundary MOD high → MOD borderline)
- score 21 vs 22 (boundary AGG borderline → AGG high)
- Q7=a with a high score (override on a non-CONSERVATIVE label)
- all answers equal (edge case for top_drivers, importance ~0.33)

### Notes for the academic PDF

- **Q7 override**: to be described in the PDF as a MiFID II Art. 25 regulatory constraint (suitability assessment), not as an algorithmic choice. The "hard rule vs probabilistic estimate" distinction is relevant for the ML Risk Profiler section.
- **`top_drivers` Phase A**: document honestly as a deterministic heuristic (proxy for SHAP). Explain that the schema was designed to be identical to Phase B — this demonstrates architectural thinking, not a patch.
- **Naming decision**: it might be worth a mini-ADR (`ADR-001-profile-label-naming.md`) to document the EN vs IT choice. The kind of documentation the professor appreciates for the coding style / decision trail criterion.
- **Citations already used in the code**: Grable & Lytton (1999), MiFID II Directive 2014/65/EU Art. 25 — to reuse verbatim in the LaTeX section.

---

## P4 — Frontend / LLM / Docs
**Estimated duration:** ~1h 30min

### What I did

- Wrote `AGENTS.md`: definition of the agent roles in the project (Code Review Agent, Test Generation Agent, Documentation Agent), description of the agentic workflow, plan for the automated PR via GitHub Actions + LLM API, evidence log for the professor's criterion 5
- Reviewed and approved `frontend/app.py` (Streamlit scaffold with 4 pages: Questionnaire, Profile Result, Portfolio Dashboard, Chat Advisor)
- Added the `render_profile()` page with `profile_label`, `confidence` and a `top_drivers` placeholder
- Wrote the complete `README.md`: header + badge, project structure, installation, usage flow, API docs (3 endpoints with JSON examples), Technical Highlights table, EU Awareness section, disclaimer, academic documentation section
- Resolved a merge conflict on `backend/data/loader.py` (origin: parallel edit by P1)
- Fixed ruff linter error F401: removed the unused `from typing import Optional` in `loader.py`
- Opened PR #5 `feature/p4-docs` → `main`, green CI, merge completed

### How I did it

- VS Code for direct editing of the files
- Integrated terminal for `git fetch`, `git merge`, `py_compile`, `pip install ruff`, `ruff check --fix`
- GitHub Desktop / GitHub web for PR management and CI verification
- Verified consistency with design v3.1 manually, following a step-by-step operational approach

### Difficulties

- Merge conflict on `backend/data/loader.py`: resolved by keeping P1's version (file under their responsibility)
- CI was failing due to an unused import (`typing.Optional`) detected by ruff: solved with `ruff check --fix`
- `uv` not available in the local PATH: solved by activating the venv and using `pip install ruff` directly

### Achievements / Key decisions

- W1 P4 closed with all the deliverables planned in design v3.1
- `app.py` already includes the HRP/Markowitz tab, EU Investor Note placeholder, session_state for the profile — structure ready for W2 without refactoring
- `README.md` covers all the professor's minimum requirements (installation, usage, API docs, user guide outlined) — to update with the real URL and docker-compose when P1 completes it
- PR #5 merged into main with green CI: clean and traceable commit history

### Next steps

- **W2 (4–10 May):** implement the complete questionnaire UI (7–10 Grable-Lytton questions), profile page with `confidence` and `top_drivers`, portfolio dashboard with weights and base metrics, connection with mock output or P1 API
- Update the `README.md` Docker section when `docker-compose.yml` is ready (P1)
- Verify with P1 that `agent_pr.yml` is planned — the professor's criterion 5, mandatory

### Notes for the academic PDF

- The process of resolving the merge conflict and the ruff linter is documentable in the "Lessons Learned" section as a concrete example of a collaborative GitHub workflow with active CI
- The choice to structure `app.py` with autonomous mock data (without dependency on the backend) ensures the frontend is always demonstrable — the "Phase A always works" pattern, consistent with design v3.1
- The use of ruff as a CI-enforced linter ensures a uniform coding style across the whole team (the professor's criterion 4)

---

# 29 April 2026 — Week 1

## P2 — Quant / Portfolio Optimization
**Estimated duration:** ~2 hours

### What I did

- Analyzed PR #4 (`define OptimizationResult interface`) and responded to Sabrina's (P1) comment on the `ERC` vs `BL` conflict in the `Literal`
- Corrected `Literal["HRP", "MV", "ERC"]` → `Literal["HRP", "MV", "BL"]` in `hrp.py` before the merge
- Wrote and posted a technical comment on GitHub PR #4 for Sabrina explaining the architectural choice (ERC = internal component, BL = standalone exposed algorithm)
- Merged PR #4 into `main` with a formal description
- Created the branch `feature/p2-hrp-optimizer`
- Added the `compute_covariance` stub (Ledoit-Wolf, W1) in `hrp.py`
- Created `tests/test_optimizer.py` with 3 structural tests
- Fixed a CI ruff error (F821 missing imports `np`, `pd`)
- Fixed a CI ruff error (I001 unordered imports)
- PR #5 opened on `feature/p2-hrp-optimizer` awaiting review

### How I did it

- All the work via the GitHub web interface (edit file, commit on branch, PR)
- `compute_covariance` stub with defensive `assert`s on empty input, NaN, and minimum number of assets
- Explicit `NotImplementedError` to signal that the implementation is deferred to W2
- Tests written to test the interface (`OptimizationResult` fields) and the stub behavior (AssertionError on invalid input, NotImplementedError on valid input)
- Lint fix: ruff-compliant import order (`from __future__` → `from typing` → `import numpy` → `import pandas`)

### Difficulties

- CI failed twice: first for missing imports (`np`, `pd`), then for import order not compliant with ruff (I001)
- Risk of committing directly to `main` out of habit — avoided thanks to the branch protection check

### Achievements / Key decisions

- **Architectural decision confirmed:** `ERC` is an internal component (aggressive tilt + regime fallback), not an exposed algorithm. `Literal["HRP", "MV", "BL"]` is the correct contract for design v3.1
- **W1 P2 completed:** all 3 tasks for the week are closed (universe_config, OptimizationResult, Ledoit-Wolf stub + tests)
- **Dependencies unblocked:** P1 has `OptimizationResult` on `main`, P3 and P4 can start integrating the interface
- **Green CI** on the `feature/p2-hrp-optimizer` branch after the lint fixes

### Next steps

- Wait for the merge of PR #5 by Sabrina
- **W2 (from Monday):** implement the real `compute_covariance` with `CovarianceShrinkage(prices).ledoit_wolf()` from PyPortfolioOpt
- W2: complete `hrp.py` with log returns, Ward clustering, recursive bisection, profile tilt, box constraints
- W2: implement `risk_metrics.py` and `markowitz.py`
- W2: add ≥3 functional tests in `test_optimizer.py`

### Notes for the academic PDF

- **ERC vs BL in the Literal:** the distinction between ERC as an internal component and BL as a standalone algorithm is an architectural choice documentable in the Portfolio Optimization section. ERC does not require estimating μ (consistent with the HRP philosophy), while BL is exposed as an explicit alternative with views derived from the profiler.
- **Ledoit-Wolf shrinkage:** the stub is already documented with a reference to Ledoit & Wolf (2004). The academic motivation (reduction of the covariance estimation error on finite samples) goes in Section 3 of the PDF and in ADR-004 (W4).
- **Defensive assertions:** every public function opens with explicit preconditions — a practice documentable as a software engineering choice in the Lessons Learned section.

---

## P3 — ML / Risk Profiling
**Week:** W1 (27 Apr – 3 May)

### What I did

- Recovered the complete project context at the start of the session: state of PR #6 (rule_based.py, P1 review pending), IT/EN label conflict resolved and pushed in the previous session.
- Produced `progetto_overview_narrativo.md` — a document in Italian for personal orientation to the project, useful for the presentation to the professor.
- Created the complete `scf_pipeline.py` scaffold with its final structure: `load_scf()`, `select_features()`, `standardise_features()`, `build_pipeline()`. Type hints and docstrings in English. `load_scf()` is a stub with `NotImplementedError` — real implementation deferred to W2.
- Downloaded and inspected `SCFP2022.csv` directly from the Fed to verify the real column names. Discovered that `RISKSCALE` does not exist in the Summary Extract — replaced with `YESFINRISK` and `NOFINRISK`. Also corrected the allocation columns (`CASH` → `CASHLI`, `REAL` removed).
- Translated the entire file into English (docstrings, comments, error messages).
- Wrote `ADR-002-scf-preprocessing.md` in English, documenting 4 decisions: SCF 2022 version, implicate=1, feature selection with mapping to the questionnaire, mandatory use of WGT.
- Committed and pushed both files on the branch `feature/p3-scf-pipeline`.
- Opened a PR on GitHub: "feat: SCF pipeline scaffold + ADR-002 preprocessing decisions" — 3 commits, all checks passed, no conflicts.
- Explored the topic of the GitHub connector and a custom MCP server.

### How I did it

I worked on the code and documents throughout the session, verifying the content against the real dataset (I downloaded and inspected `SCFP2022.csv` from the Fed) and committing manually from the terminal on iPhone. The `RISKSCALE` correction emerged precisely from direct verification on the file — not from assumptions. Each design choice was reasoned through before writing the code, in order to understand the rationale and not just copy.

### Difficulties

- Initially I did not know where the repo was (wrong directory in the terminal) — solved with `ls` and `cd robo-advisor`.
- The GitHub connector shows as "Connected" in the UI but does not expose interactive MCP tools — automated navigation of the repo is not possible. The manual flow (cp + git add/commit/push) works fine regardless.
- `RISKSCALE` does not exist in the SCF 2022 Summary Extract: discovered by verifying the CSV directly. Corrected before the final commit.

### Achievements / Key decisions

- W1 fully closed: `scf_pipeline.py` + `ADR-002` on a dedicated branch, PR opened and green.
- Empirically verified the SCF 2022 dataset: 22,975 rows (4,595 families × 5 imputations), 357 columns. Key columns confirmed: `YESFINRISK`, `NOFINRISK`, `WGT`, `EQUITY`, `BOND`, `CASHLI`, `STOCKS`.
- Understood and documented why `WGT` is mandatory: the SCF oversamples wealthy families, each row has a weight representing N real families (e.g. 3027.96 → ~3,028 families). Without WGT the model mainly learns from the behavior of the wealthy.
- Discussed the potential of a custom MCP server for Criterion 5 (AI Agents): an MCP server exposing GitHub tools would allow an agent to open PRs automatically — exactly the kind of agentic workflow the professor wants documented in `AGENTS.md`. To be explored in the next session.

### Next steps

- Wait for P1's review on PR #6 (rule_based.py) before merging both PRs.
- Verify that P1 has resolved the IT/EN label conflict in `schema.sql`.
- W2 (4–10 May): implement `load_scf()` with the real dataset, `clustering.py` with K-Means/GMM, label assignment on the clusters.
- Put the `SCFP2022.csv` dataset in the repo's `data/scf/` folder (or handle it via `.gitignore` + instructions in the README if too large for GitHub).
- Explore in the next session the construction of a custom MCP server for GitHub — useful both for the development workflow and for grading Criterion 5.

### Notes for the academic PDF

- The `implicate=1` choice is a simplification compared to Rubin's Rules (5 imputations) — to be documented honestly in the Limitations section. The rationale is that 4,595 observations are sufficient for a robust GBM and the additional complexity is not justified for this scope.
- `RISKSCALE` does not exist in the SCF 2022 Summary Extract. The SCF measures risk attitude through binary variables (`YESFINRISK`, `NOFINRISK`), not a continuous scale. This is relevant for the ML section of the PDF: the mapping between the questionnaire and SCF features is not always 1:1 — some variables must be adapted.
- The WGT value (e.g. 3027.96) has a concrete interpretation to cite in the PDF: each family in the sample represents thousands of real American families. Using the weights is not optional if you want the model to be representative of the population, not just the sample.

---

## P4 — Frontend / LLM / Docs
**Estimated duration:** ~1 hour

### What I did

- Verified the existence of `docs/` and `docs/adr/` in the local repo
- Verified the content of `frontend/app.py` (already complete with 3 pages + disclaimer)
- Created `docs/architecture.md` with data flow, component boundaries, LLM safety pipeline, failure modes and ADR table
- Created empty placeholders for ADR-001, ADR-002, ADR-003, ADR-004
- Renamed `ADR-001-db-schema.md` (P1's, was empty) to `ADR-005-db-schema.md` to avoid a numbering conflict
- Committed and pushed on `feature/p4-docs`
- Created the branch `feature/p4-streamlit-ui` (empty — app.py was already on main)
- Opened a PR on `feature/p4-docs` with Sabrina (P1) as reviewer
- Left a note in the PR about the ADR rename

### How I did it

- Terminal navigation with `git branch -a`, `ls`, `cat` to inspect the repo state
- Content of `architecture.md` written and manually reviewed
- Decision to differentiate `architecture.md` from `README.md` after a direct comparison of the two files
- Use of `git add`, `git commit`, `git push` from the terminal
- Verification on GitHub of the branch and PR state

### Difficulties

- `code` not available from the terminal (VS Code not installed in the PATH) — solved by opening the files manually from VS Code
- `feature/p4-streamlit-ui` created but turned out empty because `app.py` was already on `main` — PR not opened because it had no diff
- The first attempt at `architecture.md` was too similar to the README — rewritten in a complementary way

### Achievements / Key decisions

- W1 P4 completed: README, AGENTS.md, app.py scaffold, docs/architecture.md, ADR placeholders
- `architecture.md` correctly differentiated from the README: covers internal data flow, component boundaries, LLM safety pipeline, failure modes — content not present in the README
- ADR numbering convention established and communicated to the team via a PR comment
- PR `feature/p4-docs` opened with P1 as reviewer

### Next steps

- Wait for the review and merge of the `feature/p4-docs` PR
- W2 (from Monday): complete questionnaire UI, profile page with `profile_label` / `confidence` / `top_drivers`, portfolio dashboard with weights and metrics, connection with mock output or P1 API
- Install `code` in the PATH to open files from the terminal (`Cmd+Shift+P` → Shell Command in VS Code)
- Coordinate with P1 the ADR numbering and the content of ADR-005

### Notes for the academic PDF

- The choice to separate `architecture.md` from the README reflects a deliberate design distinction: README for the external user, architecture for the internal developer. Citable in the Frontend/UX section as an example of structured documentation.
- The Component Boundaries table (section 3 of architecture.md) is directly reusable in the LLM Narrator section of the PDF to justify the narrator pattern: "the LLM must not do: create new numbers or recommendations".
- The ADR-001 → ADR-005 rename and the communication to the team is a concrete example of agentic coordination documentable in the Lessons Learned section.
