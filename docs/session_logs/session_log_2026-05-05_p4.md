# Session Log — 2026-05-05 — Settimana 2 (Mercoledì)
**Ruolo:** P4 — Frontend / LLM / Docs  
**Durata stimata:** ~3 ore

---

## Cosa ho fatto

- Implementato `backend/llm/prompts/system_prompt.py`: template del system prompt con tutte e 9 le regole del design v3.1 (inclusa Regola 9 EU Awareness), costante `MANDATORY_DISCLAIMER`, funzione `build_system_prompt()`
- Implementato `backend/llm/narrator.py`: `NarratorClient` — scaffold completo del client Claude API con injection defence Layer 1, gestione errori, SHA-256 audit hashes, `NarratorResponse` e `NarratorError` dataclass
- Creato `backend/llm/prompts/__init__.py`
- Corretto il language setting del system prompt: rimosso "Italiano" hardcoded, sostituito con output language-adaptive ("respond in the same language the user writes in")
- Tutti i file scritti interamente in inglese (commenti, docstring, regole del prompt, fallback messages)
- Installato `anthropic` nel venv locale (`pip install anthropic`)
- Eseguito test funzionale manuale: `build_system_prompt`, injection detection, SHA-256 hash — tutti passati
- Eseguito `pytest tests/` — 1 test passato, CI verde
- Committato e pushato su branch `feature/p4-llm-narrator`
- Aggiornato il questionario Streamlit (`frontend/app.py`): sostituito questionario mock W1 con il form completo a 10 domande Grable & Lytton (1999) adattato, diviso in 3 sezioni (Who You Are Financially / How You Invest / How You React), con logica di scoring `_compute_profile()`, Q7 MiFID II hard override, borderline confidence zones, top drivers computation
- Dashboard aggiornata: legge profilo da `session_state["profile"]` invece di dati hardcoded

---

## Come l'ho fatto

- Claude come advisor tecnico per design, codice e verifica coerenza con def_2 v3.1
- VS Code per editing dei file (creazione manuale via Explorer, incolla contenuto)
- Terminale integrato VS Code per git, pip, python, pytest, ruff
- Test funzionale con file temporaneo `test_narrator_temp.py` (poi rimosso) per aggirare il limite del terminale zsh con stringhe multilinea
- GitHub per push e apertura PR

---

## Difficoltà incontrate

- `uv` non installato sul Mac → risolto usando `python` e `pip` direttamente nel `.venv`
- `code` command non nel PATH su Mac → risolto creando i file direttamente dall'Explorer di VS Code
- `zsh: parse error near ')'` sul test multilinea incollato nel terminale → risolto creando un file `.py` temporaneo nella cartella del progetto
- `ModuleNotFoundError: No module named 'backend'` eseguendo il test da `/tmp/` → risolto creando il file nella root del progetto
- Language del system prompt inizialmente in italiano per inerzia dal design doc → corretto in inglese con output language-adaptive
- `pytest` non installato nel venv → `pip install pytest`

---

## Achievement / Decisioni rilevanti

- `NarratorClient` è stateless by design: nessuna conversation history, Ground Truth JSON re-iniettato ad ogni chiamata — garantisce che il LLM sia sempre ancorato ai dati correnti
- `temperature=0.0` per output deterministico e auditabile
- `MANDATORY_DISCLAIMER` come costante condivisa tra `narrator.py` e `validator.py` (W3): un solo punto di verità, nessun rischio di drift tra i due moduli
- Layer 1 injection defence implementata prima della chiamata API: length check (800 chars) + pattern matching su 14 pattern noti
- SHA-256 hash del system prompt e del GT JSON in `NarratorResponse` → pronti per l'audit trail DB in W3
- Output language-adaptive: il LLM risponde nella lingua dell'utente, non forzato italiano
- `_compute_profile()` in `app.py` ha schema output identico al futuro GBM Phase B — nessuna modifica downstream necessaria quando il ML sarà integrato in W3

---

## Prossimi passi

- **W2 Thu-Fri (questa settimana):**
  - Aprire PR `feature/p4-llm-narrator` → `main` con description completa
  - Pagina profilo Streamlit con `profile_label`, `confidence`, `top_drivers` visualizzati correttamente
  - Collegamento frontend con `get_mock_payload()` per dashboard portfolio
  - Disclaimer UI sopra ogni output finanziario

- **W3 (settimana prossima):**
  - `backend/llm/validator.py` — 4-step validator (forbidden phrases, number check, disclaimer, injection semantic)
  - `tests/test_validator.py`
  - Wiring `narrator.py` + `validator.py` nel FastAPI `/advice` endpoint
  - Chat Advisor page collegata al backend

---

## Note per il PDF accademico

- Il pattern "Narrator, not Calculator" è implementato e documentabile: il LLM non calcola mai, narra soltanto i risultati del backend — separazione netta tra computational layer e narrative layer
- La scelta `temperature=0.0` è difendibile accademicamente: output deterministico = riproducibile = auditabile, requisito esplicito dell'audit trail
- La Regola 9 EU Awareness nel system prompt è un esempio concreto di come vincoli normativi (MiFID II + gap US/EU dati SCF) vengano implementati a livello di prompt engineering — citabile nella sezione LLM Narrator del PDF
- Il Layer 1 injection defence (pre-call) + Layer 2 semantic (Validator W3) è una pipeline di sicurezza a due livelli documentabile nella sezione "Prompt Injection Defense"
- La decisione di rendere il language output adaptive (non forzato italiano) è una scelta UX ragionata: il sistema è un prototipo accademico internazionale, non un prodotto italiano
