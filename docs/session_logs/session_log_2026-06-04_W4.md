# Session Log — 4 giugno 2026 — Settimana 4
**Ruolo:** P1 — Backend / Data Engineering
**Focus sessione:** Persistenza del questionario (pagina profilo)

---

## Cosa ho fatto

**Backend — `backend/api/main.py`**
- Aggiunto endpoint `GET /profile/latest`: dato un `session_token` nell'header, risolve lo `user_id` dalla tabella `users` e restituisce l'ultimo profilo salvato dalla tabella `recommendations`. Protetto con `verify_api_key`, nessun rate limit (è una GET leggera).
- Scritto da zero il lookup `session_token → user_id` perché nessun endpoint esistente lo faceva: `/optimize` scriveva `user_id="anonymous"` fisso.

**Frontend — `frontend/app.py`**
- Refactoring della pagina questionario per supportare 3 stati distinti:
  1. **first-time** — form vuoto, da compilare.
  2. **read-only** — profilo già presente: form nascosto, riepilogo risposte, bottone "↻ Reassess my profile".
  3. **reassessment** — form riaperto pre-popolato con le risposte precedenti; al submit salva e torna in read-only.
- Aggiunto `session_token` nell'URL come query parameter (`?sid=...`) così sopravvive al refresh della scheda.
- Creata tabella SQLite dedicata `questionnaire_profiles` (gestita direttamente dal frontend, senza toccare `backend/data/`): append-only, salva il profilo ad ogni submit e lo ricarica al reload.
- Rimosso il bottone "View my Portfolio Dashboard →" dallo stato read-only (rimane visibile solo dopo aver appena calcolato il profilo nella sessione corrente).

**Git**
- Tutto il lavoro sul branch `feature/questionnaire-persistence` (3 commit).
- Merge su `main` con risoluzione manuale di un conflitto grafico: mantenute sia la nuova architettura a 3 stati sia le modifiche UI già presenti su `main`.
- Commit finale separato per la rimozione del bottone.
- Tutto pushato su `main` sotto `Sabrina15072002`, nessun co-autore.

---

## Come l'ho fatto

- Identificato che la tabella `recommendations` non era usabile per salvare solo le risposte al questionario: ha decine di colonne `NOT NULL` pensate per l'output dell'optimizer (pesi HRP, hash dei dati di mercato, metriche di rischio) — riempirle con valori finti avrebbe inquinato l'audit trail.
- Scelto di creare una tabella separata `questionnaire_profiles`, leggera e dedicata al solo questionario, gestita con import diretto da Streamlit (senza HTTP verso FastAPI).
- Il `GET /profile/latest` è stato implementato ma reso best-effort nel frontend: se FastAPI non è raggiungibile (es. Streamlit Cloud dove gira solo Streamlit), la chiamata degrada in silenzio e il questionario usa solo `session_state` + tabella locale.

---

## Difficoltà incontrate

- Lo spec iniziale assumeva che esistesse già un pattern di lookup `session_token → user_id` nel backend — non esisteva. Implementato da zero seguendo il pattern SQLite già usato in `snapshots.py`.
- Lo spec assumeva che il frontend facesse chiamate HTTP al backend — non era mai stato così: tutto usa import diretti. Adattato di conseguenza.
- La tabella `recommendations` ha molti campi `NOT NULL` dell'optimizer che bloccavano l'insert se si tentava di usarla per salvare solo il questionario — problema scoperto durante i test.
- Conflitto di merge su `main` al momento del merge: risolto manualmente preservando entrambe le modifiche.

---

## Achievement / Decisioni rilevanti

- Persistenza del questionario operativa end-to-end: compila → submit → riga scritta nel DB → reload della pagina → profilo ripristinato in read-only.
- Architettura pulita: `questionnaire_profiles` è separata da `recommendations`, l'audit trail dell'optimizer resta intatto.
- I 3 stati del questionario funzionano correttamente e sono stati verificati sia in test headless sia nel browser reale.
- `ruff` pulito. I 2 fallimenti in `test_advice_pipeline` sono un problema preesistente (file-lock su Windows), identico su `main` prima di questa sessione — non introdotto da questo lavoro.

---

## Comportamento attuale della persistenza

La persistenza funziona finché l'URL rimane lo stesso (il `session_token` è nel query parameter `?sid=...`). Se si ricarica la pagina con lo stesso URL, il profilo viene ripristinato correttamente dallo stato read-only.

Se la scheda viene chiusa e se ne apre una nuova (senza copiare l'URL con il `?sid=`), il `session_token` cambia e il questionario riparte da zero — come se fosse un nuovo utente.

---

## Limite noto

Su Streamlit Cloud il disco è effimero: a ogni redeploy o cold start il file SQLite locale viene cancellato e la persistenza si azzera. Per una persistenza garantita anche tra deploy servirebbe un DB esterno (es. Supabase, Railway PostgreSQL) combinato con un sistema di identificazione utente stabile (es. cookie). Discusso e non implementato — decisione consapevole per non aumentare la complessità infrastrutturale a ridosso della consegna.

---

## Prossimi passi

- Decidere se cancellare il branch `feature/questionnaire-persistence` (ora mergiato su `main`).
- Valutare se il limite della persistenza su Streamlit Cloud è accettabile per la demo al prof o se vale la pena aggiungere un DB esterno.
- Se si vuole persistenza vera cross-deploy: aggiungere Supabase (free tier) come backend SQLite sostitutivo — stima 2-3 ore di lavoro.

---

## Note per il PDF accademico

- La scelta di separare `questionnaire_profiles` da `recommendations` è una decisione progettuale documentabile nella sezione Lessons Learned: separazione dei concerns tra "profilo utente" (input) e "raccomandazione ottimizzata" (output audit).
- Il limite della persistenza su Streamlit Cloud (disco effimero) è un esempio concreto di trade-off infrastrutturale da citare nella sezione Limitations.
- Il pattern di degradazione silenziosa (best-effort HTTP call → fallback su import diretto) è un esempio di design robusto per ambienti di deploy vincolati.
