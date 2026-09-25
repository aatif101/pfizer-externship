"""Offline tests for the critic contract parser (no SDK imports)."""
from __future__ import annotations

import pytest

from src.rag.critic import CriticValidationError, parse_critic_verdict


def test_parse_plain_json() -> None:
    parsed = parse_critic_verdict('{"verdict": "supported", "faithfulness": 0.9, "unsupported_claims": []}')
    assert parsed.verdict == "supported"
    assert parsed.faithfulness == 0.9


def test_parse_fenced_json_ignores_extra_keys() -> None:
    text = '```json\n{"verdict": "unsupported", "faithfulness": 0.1, "unsupported_claims": ["x"], "extra": 1}\n```'
    parsed = parse_critic_verdict(text)
    assert parsed.verdict == "unsupported"
    assert parsed.unsupported_claims == ["x"]


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"verdict": "maybe", "faithfulness": 0.5}',
        '{"verdict": "supported", "faithfulness": 1.5}',
        '{"verdict": "supported", "faithfulness": 0.5, "unsupported_claims": ["a","b","c","d","e","f"]}',
    ],
)
def test_parse_invalid_raises_critic_validation_error(text: str) -> None:
    with pytest.raises(CriticValidationError) as excinfo:
        parse_critic_verdict(text)
    assert excinfo.value.reason_code == "critic_error"
