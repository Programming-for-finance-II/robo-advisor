from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_optimization_result_has_required_fields() -> None:
    """OptimizationResult must contain all fields defined in design v3.1."""
    from backend.optimizer.hrp import OptimizationResult

    required = {
        "algorithm",
        "weights",
        "expected_return",
        "expected_volatility",
        "sharpe_ratio",
        "risk_contributions",
        "optimizer_version",
        "solver_status",
    }
    assert required.issubset(OptimizationResult.__annotations__.keys())


def test_compute_covariance_raises_on_empty_dataframe() -> None:
    """compute_covariance must raise AssertionError on empty input."""
    from backend.optimizer.hrp import compute_covariance

    with pytest.raises(AssertionError):
        compute_covariance(pd.DataFrame())


def test_compute_covariance_raises_not_implemented_on_valid_input() -> None:
    """W1 stub: NotImplementedError expected until W2 implementation."""
    from backend.optimizer.hrp import compute_covariance

    prices = pd.DataFrame(
        np.random.randn(100, 8),
        columns=["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"],
    )
    with pytest.raises(NotImplementedError):
        compute_covariance(prices)
