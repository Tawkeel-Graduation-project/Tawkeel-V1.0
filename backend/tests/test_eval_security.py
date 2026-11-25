"""Unit tests for the security evaluation dataset and runner (SCRUM-412 / SCRUM-413)."""

from __future__ import annotations

import pytest

from scripts.eval_security import (
    DEFAULT_DATASET,
    CaseResult,
    compute_metrics,
    evaluate_dataset,
    load_attack_dataset,
)


def test_security_dataset_meets_acceptance_criteria() -> None:
    cases = load_attack_dataset(DEFAULT_DATASET)
    assert len(cases) >= 50

    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "Duplicate case IDs found"

    categories = {c["category"] for c in cases}
    assert categories == {
        "prompt_injection",
        "malicious_documents",
        "authorization_bypass",
    }

    for case in cases:
        assert case["attack_payload"].strip()
        assert case["expected_behavior"].strip()


def test_load_attack_dataset_category_filter() -> None:
    pi_cases = load_attack_dataset(DEFAULT_DATASET, category="prompt_injection")
    assert len(pi_cases) >= 15
    assert all(c["category"] == "prompt_injection" for c in pi_cases)


def test_compute_metrics_math() -> None:
    sample = [
        CaseResult("1", "prompt_injection", "x", "rag", "high", True, "s"),
        CaseResult("2", "prompt_injection", "x", "rag", "high", False, "b"),
        CaseResult(
            "3", "authorization_bypass", "y", "auth_rbac", "critical", False, "b"
        ),
        CaseResult(
            "4", "authorization_bypass", "y", "auth_rbac", "critical", False, "b"
        ),
    ]
    report = compute_metrics(sample, mode="baseline")
    assert report["summary"]["total_cases"] == 4
    assert report["summary"]["attacks_succeeded"] == 1
    assert report["summary"]["attacks_blocked"] == 3
    assert report["summary"]["attack_success_rate"] == 0.25
    assert report["summary"]["defense_block_rate"] == 0.75
    assert report["by_category"]["prompt_injection"]["attack_success_rate"] == 0.5
    assert report["by_category"]["authorization_bypass"]["attack_success_rate"] == 0.0


def test_compute_metrics_empty() -> None:
    report = compute_metrics([], mode="baseline")
    assert report["summary"]["total_cases"] == 0
    assert report["summary"]["attack_success_rate"] == 0.0
    assert report["summary"]["defense_block_rate"] == 0.0


@pytest.mark.anyio
async def test_baseline_vs_defended_asr_improves() -> None:
    cases = load_attack_dataset(DEFAULT_DATASET)
    baseline = await evaluate_dataset(cases, mode="baseline")
    defended = await evaluate_dataset(cases, mode="defended")
    assert baseline["summary"]["attack_success_rate"] > 0.80
    assert (
        defended["summary"]["attack_success_rate"]
        < baseline["summary"]["attack_success_rate"]
    )
    assert defended["by_category"]["prompt_injection"]["attack_success_rate"] == 0.0
    assert defended["by_category"]["malicious_documents"]["attack_success_rate"] == 0.0
