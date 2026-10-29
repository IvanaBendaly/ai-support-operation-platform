"""Evaluate the real classifier on permitted labeled JSONL. No fabricated model scores."""

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from northstar.ai.review import assess
from northstar.config import load_settings


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    title: str
    text: str = Field(min_length=1)
    previous_text: str = ""
    sensitivity: str
    previous_sensitivity: str | None = None
    expected_needs_review: bool
    label_reason: str
    human_label_verified: bool


def summarize(rows, input_rate=None, output_rate=None):
    completed = [r for r in rows if r["assessment_status"] == "completed"]
    tp = sum(r["expected"] and r["needs_review"] for r in completed)
    fp = sum(not r["expected"] and r["needs_review"] for r in completed)
    fn = sum(r["expected"] and not r["needs_review"] for r in completed)
    tn = sum(not r["expected"] and not r["needs_review"] for r in completed)
    attempted = [r for r in rows if r["provider"] != "none"]
    timings = sorted(r["metrics"]["latency_ms"] for r in attempted)
    known_usage = all(
        all(isinstance(r["metrics"].get(k), int) for k in ("input_tokens", "output_tokens"))
        for r in attempted
    )
    cost = None
    if attempted and known_usage and input_rate is not None and output_rate is not None:
        cost = (
            sum(
                r["metrics"]["input_tokens"] * input_rate
                + r["metrics"]["output_tokens"] * output_rate
                for r in attempted
            )
            / 1_000_000
        )
    return {
        "examples": len(rows),
        "completed": len(completed),
        "attempted": len(attempted),
        "failed": sum(r["assessment_status"] == "failed" for r in rows),
        "unavailable": sum(r["assessment_status"] == "unavailable" for r in rows),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "recall_completed": tp / (tp + fn) if tp + fn else None,
        "precision_completed": tp / (tp + fp) if tp + fp else None,
        "coverage": len(completed) / len(rows) if rows else None,
        "schema_validity": sum(r["metrics"].get("schema_valid", False) for r in attempted)
        / len(attempted)
        if attempted
        else None,
        "evidence_validity": sum(r["metrics"].get("evidence_valid", False) for r in attempted)
        / len(attempted)
        if attempted
        else None,
        "latency_p50_ms": timings[(len(timings) - 1) // 2] if timings else None,
        "latency_p95_ms": timings[math.ceil(len(timings) * 0.95) - 1] if timings else None,
        "estimated_token_cost_usd": cost,
        "cost_note": "Supplied token rates only; excludes hardware. Null means unknown, not free.",
    }


def evaluate(examples, settings, provider_factory=None):
    rows = []
    for example in examples:
        current = [
            {"id": example.id + ":current", "source": "synthetic/current", "text": example.text}
        ]
        previous = (
            [
                {
                    "id": example.id + ":previous",
                    "source": "synthetic/previous",
                    "text": example.previous_text,
                }
            ]
            if example.previous_text
            else []
        )
        sensitivities = [example.sensitivity]
        if previous:
            sensitivities.append(example.previous_sensitivity or "UNCLASSIFIED")
        result = assess(
            settings, example.title, current, previous, sensitivities, [], provider_factory
        )
        # Reports deliberately omit source passages, explanations and returned quotations.
        rows.append(
            {
                "id": example.id,
                "expected": example.expected_needs_review,
                **{
                    k: v
                    for k, v in asdict(result).items()
                    if k not in {"explanation", "supporting_references"}
                },
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate dataset only; make no calls"
    )
    parser.add_argument("--allow-draft-labels", action="store_true")
    parser.add_argument("--input-usd-per-million", type=float)
    parser.add_argument("--output-usd-per-million", type=float)
    args = parser.parse_args()
    examples = [
        Example.model_validate_json(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not examples or len({e.id for e in examples}) != len(examples):
        parser.error("Dataset must contain examples with unique IDs")
    verified = all(e.human_label_verified for e in examples)
    if not args.dry_run and not verified and not args.allow_draft_labels:
        parser.error(
            "Labels require human validation; use --allow-draft-labels only for exploratory runs"
        )
    metadata = {
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "human_labels_verified": verified,
        "dry_run": args.dry_run,
        "examples": len(examples),
    }
    if not args.dry_run:
        rows = evaluate(examples, load_settings().review)
        metadata.update(
            summary=summarize(rows, args.input_usd_per_million, args.output_usd_per_million),
            results=rows,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("Evaluation report written; dry-run and label status are recorded in the report.")


if __name__ == "__main__":
    main()
