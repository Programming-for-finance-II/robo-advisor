"""
backend.schemas — Ground Truth JSON schema and mock data.

Public API:
    from backend.schemas import GroundTruthPayload, get_mock_payload
"""
from backend.schemas.ground_truth import GroundTruthPayload, build_allowed_numbers
from backend.schemas.mock_data import get_mock_payload, get_all_mock_payloads

__all__ = [
    "GroundTruthPayload",
    "build_allowed_numbers",
    "get_mock_payload",
    "get_all_mock_payloads",
]