# Session Log — 27 April 2026 — Settimana 1
**Ruolo:** P3 — ML / Risk Profiling  
**Durata stimata:** 1h30

---

## Cosa ho fatto

- Definita la struttura completa del questionario: 10 domande divise in 3 sezioni (Who You Are Financially, How You Invest, How You React)
- Discusso e scelto la metodologia Grable & Lytton (1999) come base accademica per le domande
- Definito il sistema di scoring (0–30) con confidence zones e override rule per Q7
- Prodotto il file `docs/questionnaire_schema.md` con domande, opzioni di risposta, rationale per ogni domanda e riferimenti bibliografici
- Configurato Git in locale, clonato il repo, creato il branch `feature/p3-questionnaire-schema`
- Pushato il file su GitHub e aperta la PR #1 verso main

---

## Come l'ho fatto

- Usato Claude come advisor per la struttura del questionario e la scelta metodologica
- Discusso ogni domanda e il suo mapping verso i tre profili (CONSERVATIVE, MODERATE, AGGRESSIVE)
- Eseguito i comandi Git da terminale (Mac) per clone, branch, add, commit, push
- Aperta la PR manualmente su GitHub

---

## Difficoltà incontrate

- Errore iniziale con `git add` perché il file non era ancora nella cartella `docs/` — risolto copiando il file dai Download con `cp`
- Comprensione iniziale del flusso Git (branch, PR, main) — chiarito durante la sessione

---

## Achievement / Decisioni rilevanti

- **Questionario completato e committato** — primo deliverable P3 su GitHub ✅
- **PR #1 aperta** su `feature/p3-questionnaire-schema` → main
- Scelta chiave: Q7 ha un override rule — se l'utente risponde "safety net", il profilo è cappato a CONSERVATIVE indipendentemente dal punteggio totale
- Scelta chiave: Q9 posizionata per ultima per ridurre il bias di desiderabilità sociale — difendibile accademicamente
- Confidence zones definite: borderline a 8–9, 10–11, 18–19, 20–21 → `low_confidence_flag = True`

---

## Prossimi passi

- Attendere review di P1 (emmaerba) sulla PR #1
- Iniziare `backend/ml/profiler/rule_based.py` (task mer–gio W1)
  - Implementare scoring logic dal questionario
  - Gestire override rule Q7
  - Output: `profile_label` + `confidence` + `low_confidence_flag`
- Verificare che `AGENTS.md` sia stato pushato da P4

---

## Note per il PDF accademico

- Il questionario segue la **Grable & Lytton (1999) Risk Tolerance Scale** — citazione pronta
- Le domande comportamentali (Q8, Q9) usano framing in prima persona per ridurre il bias di desiderabilità sociale — motivazione difendibile
- Q6 + Q5 insieme identificano profili asimmetrici (chi sa ma non ha mai investito, o viceversa) — punto interessante da menzionare nella sezione ML Risk Profiler
- Nella sezione Lessons Learned del PDF: menzionare l'uso di Claude come strumento di assistenza per design del questionario e documentazione
- Riferimenti bibliografici già pronti nel file: Grable & Lytton 1999, Guiso et al. 2018, Fed Reserve SCF 2022, MiFID II Art. 25
