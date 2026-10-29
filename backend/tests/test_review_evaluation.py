from northstar.evaluation.document_review import summarize


def row(expected, predicted, status="completed"):
    return {
        "expected": expected,
        "needs_review": predicted,
        "assessment_status": status,
        "provider": "ollama",
        "metrics": {
            "schema_valid": status == "completed",
            "latency_ms": 100,
            "input_tokens": 100,
            "output_tokens": 50,
        },
    }


def test_metrics_do_not_count_failed_calls_as_perfect_recall():
    result = summarize(
        [
            row(True, True),
            row(True, False),
            row(False, True),
            row(False, False),
            row(True, True, "failed"),
        ],
        1,
        2,
    )
    assert result["recall_completed"] == 0.5
    assert result["precision_completed"] == 0.5
    assert result["false_negatives"] == 1
    assert result["schema_validity"] == 0.8
    assert result["coverage"] == 0.8
    assert result["estimated_token_cost_usd"] == 0.001
    assert summarize([row(True, True, "failed")])["recall_completed"] is None
    assert summarize([])["estimated_token_cost_usd"] is None
