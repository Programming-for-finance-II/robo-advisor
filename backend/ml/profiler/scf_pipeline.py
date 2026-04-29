"""
scf_pipeline.py
---------------
Pipeline di preprocessing per il Survey of Consumer Finances (Fed, 2022).

Responsabilità:
    - Caricamento del Summary Extract SCF 2022 (CSV, implicate=1)
    - Selezione delle feature rilevanti per il profiler ML
    - Applicazione dei pesi campionari (wgt) per rappresentatività
    - Standardizzazione delle feature → output pronto per clustering.py

Riferimenti:
    - Federal Reserve (2022). Survey of Consumer Finances — Codebook and
      Methodology. https://www.federalreserve.gov/econres/scfindex.htm
    - Grable, J.E., Lytton, R.H. (1999). Financial risk tolerance revisited.
      Financial Services Review.

Note implementative (W1 — stub):
    Il dataset SCF 2022 Summary Extract non è ancora scaricato localmente.
    Le funzioni contengono la struttura corretta e la documentazione delle
    scelte di preprocessing. L'implementazione reale avviene in W2.

ADR correlato:
    docs/adr/ADR-002-scf-preprocessing.md
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Costanti — nessun magic number nel codice
# ---------------------------------------------------------------------------

# Percorso atteso del dataset SCF 2022 Summary Extract (CSV)
SCF_DEFAULT_PATH = Path("data/scf/scf2022.csv")

# Prima imputazione del SCF (1–5). Usiamo implicate=1 per semplicità.
# Motivazione: vedere ADR-002-scf-preprocessing.md
SCF_IMPLICATE = 1

# Colonne selezionate dal SCF per il profiler
# Fonte: SCF 2022 Codebook — variabili demografiche e comportamentali
SCF_FEATURE_COLUMNS: list[str] = [
    "AGE",        # Età del rispondente principale
    "INCOME",     # Reddito familiare annuo (normalizzato Fed)
    "NETWORTH",   # Patrimonio netto familiare
    "WSAVED",     # Propensione al risparmio dichiarata
    "YESFINRISK", # Disposto a rischio finanziario (1=sì, 0=no)
    "NOFINRISK",  # Non disposto a nessun rischio finanziario (1=sì, 0=no)
    "KIDS",       # Numero di figli (proxy composizione familiare)
    "EDUC",       # Livello di istruzione (proxy esperienza finanziaria)
]

# Colonne che definiscono il comportamento allocativo osservato (label source)
SCF_ALLOCATION_COLUMNS: list[str] = [
    "EQUITY",    # Valore totale in equity (azioni + fondi azionari)
    "BOND",      # Valore totale in obbligazioni
    "CASHLI",    # Valore in cash/liquidità
    "STOCKS",    # Valore diretto in azioni (sottoinsieme di EQUITY)
]

# Peso campionario obbligatorio (SCF usa design stratificato)
SCF_WEIGHT_COLUMN = "WGT"

# Soglia minima di osservazioni per procedere
MIN_OBSERVATIONS = 1_000


# ---------------------------------------------------------------------------
# Funzioni pubbliche
# ---------------------------------------------------------------------------

def load_scf(
    path: Path = SCF_DEFAULT_PATH,
    implicate: int = SCF_IMPLICATE,
) -> pd.DataFrame:
    """Carica il Summary Extract SCF 2022 e filtra per imputazione.

    Il SCF usa 5 imputazioni multiple per i dati mancanti. Per semplicità
    accademica usiamo implicate=1 (prima imputazione). Questa scelta è
    documentata come limitazione in ADR-002-scf-preprocessing.md.

    Args:
        path: Percorso al file CSV del SCF Summary Extract.
        implicate: Numero di imputazione da usare (1–5). Default: 1.

    Returns:
        DataFrame con tutte le colonne SCF per l'imputazione selezionata.

    Raises:
        FileNotFoundError: Se il file CSV non è presente al path indicato.
        ValueError: Se implicate non è in range [1, 5].
    """
    if not 1 <= implicate <= 5:
        raise ValueError(f"implicate deve essere tra 1 e 5, ricevuto: {implicate}")

    if not path.exists():
        raise FileNotFoundError(
            f"Dataset SCF non trovato in: {path}\n"
            "Scarica il Summary Extract 2022 da:\n"
            "https://www.federalreserve.gov/econres/scfindex.htm"
        )

    logger.info("Caricamento SCF da %s (implicate=%d)...", path, implicate)

    # TODO (W2): implementare il caricamento reale
    # Il SCF CSV ha una colonna 'Y1' o 'IMPLICATE' che identifica l'imputazione
    # df = pd.read_csv(path, low_memory=False)
    # df = df[df["Y1"] == implicate].reset_index(drop=True)

    raise NotImplementedError(
        "load_scf() — implementazione W2. "
        "Il dataset SCF 2022 deve essere scaricato prima di procedere."
    )


def select_features(df: pd.DataFrame) -> pd.DataFrame:
    """Seleziona e rinomina le colonne rilevanti dal DataFrame SCF grezzo.

    Mantiene le feature demografiche/comportamentali, le colonne di
    allocazione (per il clustering) e il peso campionario.

    Args:
        df: DataFrame SCF grezzo restituito da load_scf().

    Returns:
        DataFrame con solo le colonne necessarie alla pipeline.

    Raises:
        ValueError: Se colonne obbligatorie mancano nel DataFrame.
    """
    required = SCF_FEATURE_COLUMNS + SCF_ALLOCATION_COLUMNS + [SCF_WEIGHT_COLUMN]
    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(
            f"Colonne mancanti nel dataset SCF: {missing}\n"
            "Verifica il Codebook SCF 2022 per i nomi corretti delle variabili."
        )

    logger.info("Selezione di %d feature + %d allocation columns + weight.",
                len(SCF_FEATURE_COLUMNS), len(SCF_ALLOCATION_COLUMNS))

    # TODO (W2): aggiungere eventuali feature engineered
    # es. EQUITY_RATIO = EQUITY / (EQUITY + BOND + CASH + REAL)

    return df[required].copy()


def standardise_features(
    df: pd.DataFrame,
    feature_cols: Optional[list[str]] = None,
) -> tuple[pd.DataFrame, StandardScaler]:
    """Standardizza le feature numeriche (zero mean, unit variance).

    I pesi campionari (WGT) e le colonne di allocazione non vengono
    standardizzate — rimangono nel DataFrame come colonne ausiliarie.

    Args:
        df: DataFrame con feature selezionate (output di select_features()).
        feature_cols: Lista di colonne da standardizzare.
                      Default: SCF_FEATURE_COLUMNS.

    Returns:
        Tuple (df_standardised, scaler) dove scaler è fitted e
        può essere riusato per trasformare nuovi utenti a runtime.
    """
    if feature_cols is None:
        feature_cols = SCF_FEATURE_COLUMNS

    cols_to_scale = [col for col in feature_cols if col in df.columns]

    scaler = StandardScaler()
    df_out = df.copy()
    df_out[cols_to_scale] = scaler.fit_transform(df[cols_to_scale])

    logger.info("Standardizzazione completata su %d colonne.", len(cols_to_scale))

    return df_out, scaler


def build_pipeline(
    path: Path = SCF_DEFAULT_PATH,
    implicate: int = SCF_IMPLICATE,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, StandardScaler]:
    """Entry point principale della pipeline SCF.

    Esegue in sequenza: load → select → standardise.

    Args:
        path: Percorso al file CSV del SCF.
        implicate: Imputazione da usare (default: 1).

    Returns:
        Tuple (X, alloc, weights, scaler) dove:
            X       — feature standardizzate (n_samples × n_features)
            alloc   — colonne di allocazione raw per clustering (n_samples × 4)
            weights — pesi campionari SCF (n_samples,)
            scaler  — StandardScaler fitted su X

    Example:
        >>> X, alloc, weights, scaler = build_pipeline()
        >>> # X è pronto per clustering.py
        >>> # alloc è pronto per costruire i label via K-Means/GMM
    """
    df_raw = load_scf(path=path, implicate=implicate)
    df_selected = select_features(df_raw)
    df_std, scaler = standardise_features(df_selected)

    if len(df_std) < MIN_OBSERVATIONS:
        raise ValueError(
            f"Troppo poche osservazioni dopo il filtraggio: {len(df_std)} "
            f"(minimo richiesto: {MIN_OBSERVATIONS})"
        )

    X = df_std[SCF_FEATURE_COLUMNS].to_numpy()
    alloc = df_selected[SCF_ALLOCATION_COLUMNS]
    weights = df_selected[SCF_WEIGHT_COLUMN].to_numpy()

    logger.info(
        "Pipeline SCF completata: %d osservazioni, %d feature.",
        len(X), X.shape[1],
    )

    return X, alloc, weights, scaler
