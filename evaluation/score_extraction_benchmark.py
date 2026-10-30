"""Score extraction benchmark results without changing any extracted values."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name",
               "subtotal", "tax", "discount", "total", "currency"]
OPTIONAL_FIELDS = ["shipping", "other_charges", "payments_received", "balance_due"]
ITEM_FIELDS = ["description", "quantity", "unit", "unit_price", "line_total", "tax", "discount"]


def norm(value):
    return " ".join(str(value).split()).casefold() if value is not None else None


def decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("%", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def equal(field: str, expected, actual) -> bool:
    if expected is None or actual is None:
        return expected is actual
    if field == "invoice_date":
        try:
            return datetime.strptime(str(actual), "%Y-%m-%d").date().isoformat() == str(expected)
        except ValueError:
            return False
    if field in CORE_FIELDS + OPTIONAL_FIELDS or field in {"quantity", "unit_price", "line_total"}:
        if field in {"tax", "discount"} and "%" in str(expected):
            return decimal(expected) == decimal(actual) and str(actual).strip().endswith("%")
        return decimal(expected) == decimal(actual)
    return norm(expected) == norm(actual)


def scalar_value(extracted: dict, field: str):
    value = extracted.get(field)
    return value.get("value") if isinstance(value, dict) else None


def score_field(field: str, expected, actual) -> dict:
    if expected is None:
        return {"expected_null": True, "null_correct": actual is None,
                "hallucination": actual is not None, "correct": False}
    if actual is None:
        return {"expected_null": False, "null_correct": False, "hallucination": False, "correct": False}
    return {"expected_null": False, "null_correct": False, "hallucination": not equal(field, expected, actual),
            "correct": equal(field, expected, actual)}


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * p
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return round(values[lower], 2)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 2)


def score_line_items(expected_items, actual_items):
    actual_items = actual_items or []
    metrics = {"correct": 0, "applicable": 0, "missing": 0, "hallucinations": 0, "extra_items": 0}
    for index, expected in enumerate(expected_items):
        actual = actual_items[index] if index < len(actual_items) else {}
        for field in ITEM_FIELDS:
            result = score_field(field, expected.get(field), actual.get(field))
            if expected.get(field) is not None:
                metrics["applicable"] += 1
                metrics["correct"] += int(result["correct"])
                metrics["missing"] += int(actual.get(field) is None)
                metrics["hallucinations"] += int(result["hallucination"])
    metrics["extra_items"] = max(0, len(actual_items) - len(expected_items))
    metrics["hallucinations"] += metrics["extra_items"]
    return metrics


def load_pricing(path: Path | None):
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def cost(tokens, model, pricing):
    if not pricing or not model or model not in pricing:
        return None
    rates = pricing[model]
    if rates.get("input_per_1m") is None or rates.get("output_per_1m") is None:
        return None
    return ((tokens["input"] / 1_000_000) * float(rates["input_per_1m"]) +
            (tokens["output"] / 1_000_000) * float(rates["output_per_1m"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="evaluation/extraction_dataset/labels.json")
    parser.add_argument("--results", default="evaluation/extraction_results.json")
    parser.add_argument("--expected-results", default="evaluation/extraction_expected_results.json")
    parser.add_argument("--pricing", default="evaluation/pricing.json")
    parser.add_argument("--report", default="evaluation/EVALUATION_REPORT.md")
    args = parser.parse_args()
    labels = json.loads((ROOT / args.labels).read_text(encoding="utf-8"))
    results = json.loads((ROOT / args.results).read_text(encoding="utf-8"))
    expected_path = ROOT / args.expected_results
    expected = json.loads(expected_path.read_text(encoding="utf-8")) if expected_path.exists() else {"results": []}
    by_name = {d["filename"]: d for d in labels["documents"]}
    field_stats = {field: {"correct": 0, "applicable": 0, "missing": 0, "hallucinations": 0,
                           "null_expected": 0, "null_correct": 0} for field in CORE_FIELDS + OPTIONAL_FIELDS}
    line_stats = {"correct": 0, "applicable": 0, "missing": 0, "hallucinations": 0, "extra_items": 0}
    valid_results = [r for r in results["results"] if r["filename"] in by_name]
    latencies = {}
    needs_review = 0
    tokens = {"input": 0, "output": 0}
    token_known = False
    models = set()
    misses = []
    for result in valid_results:
        truth = by_name[result["filename"]]["ground_truth"]
        extracted = result.get("raw_extracted") or {}
        needs_review += int(bool(result.get("needs_review")))
        if result.get("model"):
            models.add(result["model"])
        for key, usage_key in (("input_tokens", "input"), ("output_tokens", "output")):
            if result.get(key) is not None:
                tokens[usage_key] += int(result[key])
                token_known = True
        latencies.setdefault(result["document_type"], []).append(result["processing_time_ms"])
        for field in CORE_FIELDS + OPTIONAL_FIELDS:
            outcome = score_field(field, truth.get(field), scalar_value(extracted, field))
            stats = field_stats[field]
            stats["correct"] += int(outcome["correct"])
            stats["applicable"] += int(truth.get(field) is not None)
            stats["missing"] += int(truth.get(field) is not None and scalar_value(extracted, field) is None)
            stats["hallucinations"] += int(outcome["hallucination"])
            stats["null_expected"] += int(truth.get(field) is None)
            stats["null_correct"] += int(truth.get(field) is None and scalar_value(extracted, field) is None)
            if truth.get(field) is not None and not outcome["correct"]:
                misses.append((field, result["filename"], truth.get(field), scalar_value(extracted, field)))
        line = score_line_items(truth["line_items"], extracted.get("line_items"))
        for key in line_stats:
            line_stats[key] += line[key]

    total_correct = sum(s["correct"] for s in field_stats.values()) + line_stats["correct"]
    total_applicable = sum(s["applicable"] for s in field_stats.values()) + line_stats["applicable"]
    total_hallucinations = sum(s["hallucinations"] for s in field_stats.values()) + line_stats["hallucinations"]
    consistency = {}
    for filename in by_name:
        runs = [r for r in valid_results if r["filename"] == filename]
        signatures = [json.dumps(r.get("raw_extracted"), sort_keys=True) for r in runs]
        consistency[filename] = len(set(signatures)) == 1
    pricing = load_pricing(ROOT / args.pricing)
    model = sorted(models)[0] if len(models) == 1 else ("multiple" if models else None)
    estimated_cost = cost(tokens, model, pricing) if token_known else None
    valid_success = sum(r.get("document_status") in {"completed", "needs_review"} for r in valid_results)
    report = [
        "# Extraction benchmark report",
        "",
        "## Scope",
        f"- Valid documents: {len(labels['documents'])}; recorded valid runs: {len(valid_results)}.",
        f"- Composition: 8 digital PDFs, 4 degraded images, 3 spreadsheets.",
        f"- Expected-failure files: {len(labels['expected_failures'])}; separate runs recorded: {len(expected['results'])}.",
        "- Repeated runs are measurements of the same document, not additional documents.",
        "",
        "## Accuracy and error metrics",
        f"- Overall field accuracy: {total_correct}/{total_applicable} = "
        f"{(total_correct / total_applicable * 100 if total_applicable else 0):.2f}% "
        "(denominator: non-null ground-truth scalar and line-item fields).",
        f"- Hallucinations: {total_hallucinations} incorrect non-null predictions.",
        f"- Missing predictions: {sum(s['missing'] for s in field_stats.values()) + line_stats['missing']}.",
        f"- Expected-null correctness: {sum(s['null_correct'] for s in field_stats.values())}/"
        f"{sum(s['null_expected'] for s in field_stats.values())}.",
        f"- Needs-review rate: {needs_review}/{len(valid_results)} = "
        f"{(needs_review / len(valid_results) * 100 if valid_results else 0):.2f}%.",
        "",
        "| Field | Correct | Applicable | Accuracy | Missing | Hallucinations |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for field, stats in field_stats.items():
        report.append(f"| {field} | {stats['correct']} | {stats['applicable']} | "
                      f"{(stats['correct'] / stats['applicable'] * 100 if stats['applicable'] else 0):.2f}% | "
                      f"{stats['missing']} | {stats['hallucinations']} |")
    report.extend([
        f"| line_item_fields | {line_stats['correct']} | {line_stats['applicable']} | "
        f"{(line_stats['correct'] / line_stats['applicable'] * 100 if line_stats['applicable'] else 0):.2f}% | "
        f"{line_stats['missing']} | {line_stats['hallucinations']} |",
        "",
        "## Reliability and latency",
        f"- Valid-document processing success: {valid_success}/{len(valid_results)} = "
        f"{(valid_success / len(valid_results) * 100 if valid_results else 0):.2f}%.",
        f"- Run-to-run exact-result consistency: {sum(consistency.values())}/{len(consistency)} documents.",
    ])
    for kind, values in latencies.items():
        report.append(f"- {kind} processing latency: p50={percentile(values, .50)} ms; "
                      f"p95={percentile(values, .95)} ms; n={len(values)}.")
    report.extend([
        "",
        "## Token usage and cost",
        f"- Models observed: {', '.join(sorted(models)) if models else 'none recorded'}.",
        f"- Input tokens: {tokens['input'] if token_known else 'null'}; "
        f"output tokens: {tokens['output'] if token_known else 'null'}.",
        f"- Estimated API cost: {f'${estimated_cost:.6f}' if estimated_cost is not None else 'unavailable'} "
        "(requires provider usage and an explicit local pricing.json with pricing date).",
        "",
        "## Ten worst misses",
        "| Filename | Field | Expected | Actual |",
        "|---|---|---|---|",
    ])
    for field, filename, expected_value, actual_value in misses[:10]:
        report.append(f"| {filename} | {field} | {expected_value!s} | {actual_value!s} |")
    report.extend([
        "",
        "Expected-failure outcomes are stored separately in `extraction_expected_results.json` "
        "and are excluded from valid-document accuracy denominators.",
    ])
    output = ROOT / args.report
    output.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "valid_runs": len(valid_results),
                      "overall_field_accuracy": total_correct / total_applicable if total_applicable else None,
                      "estimated_cost": estimated_cost}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
