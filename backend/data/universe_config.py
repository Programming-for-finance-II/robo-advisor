# backend/data/universe_config.py
"""
ETF Universe Configuration 
==================================
Defines the 8-asset hybrid universe.

Design rationale:
- Each ETF has a UCITS primary ticker (dual-listed where available) and
  a US-listed fallback for cases where yfinance returns excessive NaN values.
- The ValidatedDataLoader in loader.py consumes get_fallback_map() to
  implement automatic UCITS fallback logic.
- Clusters reflect correlation structure under normal and stress regimes,
  used by hrp.py for Ward linkage and by risk_metrics.py for cluster
  constraint enforcement.

Consumed by:
  - backend/data/loader.py          (fallback logic, UCITS audit)
  - backend/optimizer/hrp.py        (tickers, cluster labels)
  - backend/optimizer/risk_metrics.py (cluster constraints)
  - tests/test_ucits_fallback.py    (integrity checks)

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ClusterLabel = Literal["risk_assets", "real_assets", "safe_haven", "cash"]

# Asset-level weight constraints (post-optimisation guardrails)
ASSET_WEIGHT_MIN: float = 0.05
ASSET_WEIGHT_MAX: float = 0.40

# Cluster-level weight constraints
CLUSTER_WEIGHT_MIN: float = 0.10
CLUSTER_WEIGHT_MAX: float = 0.60


# ---------------------------------------------------------------------------
# ETFDefinition dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ETFDefinition:
    """
    Immutable descriptor for a single ETF in the universe.

    Attributes
    ----------
    primary_ticker : str
        Preferred ticker — UCITS-wrapped where available (e.g. CSPX.L).
        Used as the default by the DataLoader.
    fallback_ticker : str
        US-listed fallback activated when primary has NaN ratio > 2%.
        Must expose equivalent economic exposure to primary.
    asset_class : str
        Human-readable asset class label (used in UI and PDF).
    cluster : ClusterLabel
        Structural cluster for HRP linkage and constraint enforcement.
    currency : str
        Denomination currency of the *primary* ticker.
    is_ucits : bool
        True if primary_ticker is a UCITS-compliant instrument.
    rationale : str
        One-sentence academic justification for inclusion and design choice.
        Referenced in ADR-004 and LaTeX Section 3.
    """

    primary_ticker: str
    fallback_ticker: str
    asset_class: str
    cluster: ClusterLabel
    currency: str
    is_ucits: bool
    rationale: str


# ---------------------------------------------------------------------------
# Universe v3.1 — 8 ETF, UCITS-aware
# ---------------------------------------------------------------------------
#
# Cluster structure expected under normal regime:
#
#   Cluster A — risk_assets   : CSPX.L / EFA      (equity beta)
#   Cluster B — real_assets   : GLD / VNQ          (inflation / real)
#   Cluster C — safe_haven    : AGGH.MI / TLT / TIP (duration / deflation)
#   Cluster D — cash          : XEON.MI             (overnight rate)

ETF_UNIVERSE: list[ETFDefinition] = [
    # ------------------------------------------------------------------ #
    # Cluster A — Risk Assets                                            #
    # ------------------------------------------------------------------ #
    ETFDefinition(
        primary_ticker="CSPX.L",
        fallback_ticker="SPY",
        asset_class="Equity USA",
        cluster="risk_assets",
        currency="USD",
        is_ucits=True,
        rationale=(
            "S&P 500 exposure via UCITS wrapper (iShares Core S&P 500 UCITS ETF). "
            "Same underlying as SPY; preferred for EU investor eligibility under MiFID II."
        ),
    ),
    ETFDefinition(
        primary_ticker="EFA",
        fallback_ticker="EFA",
        asset_class="Equity International",
        cluster="risk_assets",
        currency="USD",
        is_ucits=False,
        rationale=(
            "MSCI EAFE exposure (developed markets ex-US). "
            "No UCITS equivalent with comparable liquidity and yfinance coverage; "
            "US-listed ticker retained as both primary and fallback."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Cluster B — Real Assets                                            #
    # ------------------------------------------------------------------ #
    ETFDefinition(
        primary_ticker="GLD",
        fallback_ticker="GLD",
        asset_class="Gold",
        cluster="real_assets",
        currency="USD",
        is_ucits=False,
        rationale=(
            "Gold via SPDR Gold Shares. Flight-to-quality and inflation hedge; "
            "low or negative correlation with equities in stress regimes. "
            "UCITS equivalent (SGLN.L) excluded due to lower yfinance data quality."
        ),
    ),
    ETFDefinition(
        primary_ticker="VNQ",
        fallback_ticker="VNQ",
        asset_class="Real Estate (REIT)",
        cluster="real_assets",
        currency="USD",
        is_ucits=False,
        rationale=(
            "Vanguard Real Estate ETF — US REIT exposure. "
            "Provides inflation pass-through via rent income and partial equity beta. "
            "Contributes to cluster diversification relative to pure equity positions."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Cluster C — Safe Haven / Duration                                  #
    # ------------------------------------------------------------------ #
    ETFDefinition(
        primary_ticker="AGGH.MI",
        fallback_ticker="AGG",
        asset_class="Bond Aggregate EUR-Hedged",
        cluster="safe_haven",
        currency="EUR",
        is_ucits=True,
        rationale=(
            "iShares Core Global Aggregate Bond UCITS ETF (EUR-hedged). "
            "Shifts aggregate bond exposure to EUR denomination, reducing FX risk "
            "for EU investors relative to USD-denominated AGG."
        ),
    ),
    ETFDefinition(
        primary_ticker="TLT",
        fallback_ticker="TLT",
        asset_class="US Treasury Long Duration",
        cluster="safe_haven",
        currency="USD",
        is_ucits=False,
        rationale=(
            "iShares 20+ Year Treasury Bond ETF. "
            "High-duration safe-haven asset; strongly negative correlation "
            "with equities during deflationary shocks (GFC 2008, COVID 2020). "
            "Complements AGGH.MI with explicit duration tilt."
        ),
    ),
    ETFDefinition(
        primary_ticker="TIP",
        fallback_ticker="TIP",
        asset_class="US TIPS (Inflation-Linked)",
        cluster="safe_haven",
        currency="USD",
        is_ucits=False,
        rationale=(
            "iShares TIPS Bond ETF. Inflation breakeven exposure; "
            "diversifies duration risk within the safe_haven cluster "
            "by providing real yield rather than nominal yield. "
            "Retained for diversification vs AGGH.MI."
        ),
    ),
    # ------------------------------------------------------------------ #
    # Cluster D — Cash / Overnight                                       #
    # ------------------------------------------------------------------ #
    ETFDefinition(
        primary_ticker="XEON.MI",
        fallback_ticker="BIL",
        asset_class="Cash / Overnight",
        cluster="cash",
        currency="EUR",
        is_ucits=True,
        rationale=(
            "Xtrackers EUR Overnight Rate Swap UCITS ETF. "
            "EUR overnight rate proxy (€STR); replaces USD T-Bill (BIL) "
            "as the cash position for EU investor portfolios. "
            "Minimum allocation floor ensures liquidity buffer in all profiles."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Helper functions — consumed by DataLoader and Optimizer
# ---------------------------------------------------------------------------

def get_primary_tickers() -> list[str]:
    """Return ordered list of primary tickers for all ETFs in the universe."""
    return [e.primary_ticker for e in ETF_UNIVERSE]


def get_fallback_map() -> dict[str, str]:
    """
    Return {primary_ticker: fallback_ticker} mapping.

    Used by ValidatedDataLoader to substitute tickers with NaN ratio > 2%.
    If primary == fallback, no substitution is needed (US-only tickers).
    """
    return {e.primary_ticker: e.fallback_ticker for e in ETF_UNIVERSE}


def get_ucits_tickers() -> list[str]:
    """Return primary tickers that are UCITS-compliant instruments."""
    return [e.primary_ticker for e in ETF_UNIVERSE if e.is_ucits]


def get_cluster_map() -> dict[str, ClusterLabel]:
    """Return {primary_ticker: cluster_label} mapping for all ETFs."""
    return {e.primary_ticker: e.cluster for e in ETF_UNIVERSE}


def get_tickers_by_cluster(cluster: ClusterLabel) -> list[str]:
    """Return primary tickers belonging to a given cluster."""
    return [e.primary_ticker for e in ETF_UNIVERSE if e.cluster == cluster]


def get_universe_summary() -> list[dict]:
    """
    Return a list of dicts for quick inspection and UI display.

    Useful for Streamlit tables and DataLoader logs.
    """
    return [
        {
            "primary": e.primary_ticker,
            "fallback": e.fallback_ticker,
            "asset_class": e.asset_class,
            "cluster": e.cluster,
            "currency": e.currency,
            "is_ucits": e.is_ucits,
        }
        for e in ETF_UNIVERSE
    ]


# ---------------------------------------------------------------------------
# Integrity assertions — run at import time
# ---------------------------------------------------------------------------

def _validate_universe() -> None:
    """
    Lightweight structural assertions checked at module import.

    Raises AssertionError if the universe violates expected invariants.
    These are NOT unit tests — they guard against accidental misconfiguration.
    """
    tickers = get_primary_tickers()

    assert len(ETF_UNIVERSE) == 8, (
        f"Universe must contain exactly 8 ETFs, got {len(ETF_UNIVERSE)}"
    )

    assert len(tickers) == len(set(tickers)), (
        "Duplicate primary tickers detected in ETF_UNIVERSE"
    )

    expected_clusters: set[ClusterLabel] = {
        "risk_assets", "real_assets", "safe_haven", "cash"
    }
    actual_clusters = {e.cluster for e in ETF_UNIVERSE}
    assert actual_clusters == expected_clusters, (
        f"Missing clusters: {expected_clusters - actual_clusters}"
    )

    ucits_count = sum(1 for e in ETF_UNIVERSE if e.is_ucits)
    assert ucits_count >= 3, (
        f"Design requires at least 3 UCITS tickers, found {ucits_count}"
    )

    for e in ETF_UNIVERSE:
        assert e.primary_ticker, "Empty primary_ticker found"
        assert e.fallback_ticker, "Empty fallback_ticker found"
        assert e.rationale, f"Missing rationale for {e.primary_ticker}"


_validate_universe()
