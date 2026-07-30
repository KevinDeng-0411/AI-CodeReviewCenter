"""C3 evidence collector parsing regression tests."""

import json

from collect_c3_evidence import EvidenceFailure, extract_metrics


def _metrics() -> dict:
    return {
        "chat": {"sse_fidelity": 1.0},
        "retrieval": {
            "cases": 30,
            "rrf": {"recall@5": 1.0},
        },
    }


def test_extract_metrics_accepts_pytest_progress_prefix():
    payload = json.dumps(_metrics(), sort_keys=True)
    assert extract_metrics(f"...[C3 METRICS] {payload}\n.") == _metrics()


def test_extract_metrics_rejects_incomplete_baseline():
    payload = _metrics()
    payload["retrieval"]["cases"] = 29
    try:
        extract_metrics("[C3 METRICS] " + json.dumps(payload))
    except EvidenceFailure as exc:
        assert "30 cases" in str(exc)
    else:
        raise AssertionError("incomplete golden set must be rejected")
