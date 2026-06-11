# Session Log — 2026-05-08 — Settimana 2

**Ruolo:** P4 — Frontend / LLM / Docs  
**Durata stimata:** ~1 ora

---

## Cosa ho fatto

- Aggiornato `_QUESTIONS` in `frontend/app.py` con le domande del questionario
- Creato `docs/report.tex`: skeleton LaTeX completo con tutte e 8 le sezioni previste dal dev plan (Introduction, ML Risk Profiler, Portfolio Optimisation, LLM Narrator, Backtest Results, Limitations, Lessons Learned, Conclusions)
- Creato `docs/references.bib` con le 4 citazioni fondamentali del progetto (López de Prado 2016, Ledoit-Wolf 2004, Fed SCF 2022, MiFID II)
- Impostato il preamble LaTeX con tutti i package necessari (amsmath, booktabs, biblatex/biber, listings, hyperref)
- Strutturata la Sezione 4 (LLM Narrator) con subsection già popolate: Narrator pattern, Ground Truth JSON contract, System Prompt rules, Validator 4-step pipeline, Prompt Injection Defence
- Inserita la tabella backtest (Sezione 5) con struttura pronta per i numeri di P2
- Inseriti `% TODO` espliciti per ogni sezione di competenza P2/P3, così possono scrivere in autonomia
- Definito il workflow di compilazione: `pdflatex → biber → pdflatex × 2`

## Come l'ho fatto

- Claude come advisor tecnico per struttura LaTeX e verifica coerenza con dev plan e design v3.1
- Confronto con screenshot del dev plan PDF (W4 Wed–Thu task list) per coprire tutte le sezioni richieste
- Contenuto della Sezione 4 derivato da: `docs/ground_truth_schema.md`, `system_prompt.py`, piano del validator 4-step

## Difficoltà incontrate

- Nessuna difficoltà tecnica rilevante nella sessione

## Achievement / Decisioni rilevanti

- **Skeleton LaTeX completato in W2** — vantaggio tattico: P2 e P3 hanno già il file e i `% TODO` marcati, possono scrivere le loro sezioni in parallelo durante W3 senza aspettare W4
- La Sezione 4 (LLM Narrator) è già abbozzata con il contenuto giusto: Ground Truth JSON contract, regole del system prompt, 4-step validator — in W4 sarà solo da espandere, non da costruire da zero
- `references.bib` con López de Prado e Ledoit-Wolf già citati correttamente nel testo — nessun placeholder da cercare in fretta all'ultimo

## Prossimi passi

- Comunicare a P2 e P3 che `docs/report.tex` esiste e i loro `% TODO` sono nelle sezioni 2 e 3
- W2 rimanente: pagina profilo (`profile_label`, `confidence`, `top_drivers`), dashboard portfolio, disclaimer UI, Chat Advisor placeholder
- W3: implementare `narrator.py` e `validator.py` — la Sezione 4 del LaTeX si popola quasi automaticamente
- W4 Wed–Thu: completare i `% TODO` di Sezione 4, 6, 7, 8 e integrare le sezioni di P2/P3

## Note per il PDF accademico

- La scelta di creare lo skeleton in W2 (invece di W4) è documentabile nella sezione Lessons Learned come esempio di gestione proattiva delle dipendenze: la documentazione non è stata lasciata all'ultimo
- La struttura della Sezione 4 — separazione netta tra "narrator" e "calculator" — è la scelta architetturale centrale dell'intero layer LLM; vale una subsection dedicata nella sezione Lessons Learned oltre che nella Sezione 4 stessa
- Le 4 citazioni in `references.bib` coprono le due scelte algoritmiche ★ Advanced (HRP, Ledoit-Wolf) e i due vincoli normativi (SCF US-centrism, MiFID II) — allineamento diretto con i criteri 1 e 3 del prof.
