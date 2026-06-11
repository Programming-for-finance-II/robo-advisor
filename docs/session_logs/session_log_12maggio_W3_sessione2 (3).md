# Session Log — 12 maggio 2026 — Settimana 3 (sessione 2)
**Ruolo:** P1 — Backend / Data Engineering  
**Durata stimata:** 2 ore

---

## Cosa ho fatto

- Configurato `ANTHROPIC_API_KEY` come secret in GitHub Actions
- Impostato limite di spesa mensile $5 su Anthropic Console
- Creato API key `robo-advisor-usi-2026` su console.anthropic.com
- Scritto `.github/workflows/agent_pr.yml` da zero (il file era vuoto):
  - Trigger: `workflow_dispatch` + push a `backend/optimizer/`
  - Legge tutti i file Python in `backend/optimizer/`
  - Chiama Claude API (`claude-sonnet-4-5`) per generare/migliorare docstrings
  - Committa su branch `agent/optimizer-docstrings-{run_number}`
  - Apre PR automaticamente via `gh pr create`
- Risolto errore modello deprecato (`claude-sonnet-4-20250514` → `claude-sonnet-4-5`)
- Risolto errore permessi PR (`GITHUB_TOKEN` non autorizzato) → creato PAT con 90 giorni di validità, aggiunto come secret `PAT_TOKEN`
- Abilitato `PAT_TOKEN` nel workflow al posto di `GITHUB_TOKEN`
- Triggerato workflow con successo → **PR #43 aperta automaticamente** da AI agent
- Creato `backend/llm/input_sanitiser.py`:
  - Limit 500 chars
  - Keyword blocking (14 pattern noti)
  - Wrap in `<user_input>` tag
- Wirato `sanitise()` nell'endpoint `/advice` come Layer 1 pre-call
- Scritto e mergiato `docs/adr/ADR-003-cloud-deploy.md`:
  - Streamlit Community Cloud vs Railway
  - Decisione motivata con pro/contro
  - Limitazioni SQLite documentate
  - Railway come fallback documentato

---

## Come l'ho fatto

- Identificato che il problema dei permessi PR era a livello organizzazione GitHub — non modificabile dalle impostazioni standard
- Usato PAT (Personal Access Token) con scope `repo` + `workflow` come workaround
- Modello Claude aggiornato leggendo il messaggio di deprecazione nel log del workflow
- `input_sanitiser.py` scritto come modulo indipendente per separation of concerns — Layer 1 separato da Layer 2 (NarratorClient) e Layer 3 (validator.py)

---

## Difficoltà incontrate

- `GITHUB_TOKEN` non autorizzato ad aprire PR in repo di organizzazione privata — risolto con PAT
- Impostazioni Workflow permissions non modificabili né dal repo né dall'organizzazione — limitazione GitHub per organizzazioni
- Modello `claude-sonnet-4-20250514` deprecato — aggiornato a `claude-sonnet-4-5`
- La modifica del modello non arrivava in `main` per via di branch/merge confusion — risolto modificando direttamente su `main`

---

## Achievement / Decisioni rilevanti

- ✅ **Criterio 5 completato** — `agent_pr.yml` funzionante, PR #43 aperta da AI agent
- ✅ PR #43 URL: https://github.com/Programming-for-finance-II/robo-advisor/pull/43
- ✅ `input_sanitiser.py` — Layer 1 defence wirато in `/advice`
- ✅ `ADR-003-cloud-deploy.md` — deliverable accademico W3 completato
- Decisione: PAT con 90 giorni di validità (scade agosto 2026) — copre la correzione del prof
- Decisione: PR #43 lasciata aperta intenzionalmente come evidence per AGENTS.md

---

## Prossimi passi

- DB hardening — `validator_flags`, `retry_count`, `fallback_triggered` loggati correttamente (Fri)
- Integration test pipeline `/profile` → `/optimize` → `/advice` end-to-end (Fri)
- Comunicare URL PR #43 a Elena per AGENTS.md evidence
- Deploy Streamlit Cloud (W4 — ma de-riskare prima possibile)

---

## Note per il PDF accademico

- **Criterio 5 evidence:** PR #43 aperta automaticamente da GitHub Actions + Claude API — citabile nella sezione AI Agents come esempio concreto di agentic workflow
- **PAT workaround:** esempio di problem-solving infrastrutturale — le restrizioni GitHub delle organizzazioni private non permettono `GITHUB_TOKEN` per aprire PR. Soluzione: PAT con scope limitato. Citabile in Lessons Learned come limitazione dell'ambiente
- **input_sanitiser.py:** Layer 1 della pipeline di sicurezza LLM — separation of concerns tra pre-call defence (sanitiser), mid-call (NarratorClient) e post-call (validator). Citabile nella sezione LLM Safety
- **ADR-003:** SQLite non persiste tra redeploy su Streamlit Cloud — limitazione documentata, accettata per il prototipo universitario. Citabile in Section 6 (Limitations)
