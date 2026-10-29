"""Reproducible, dependency-light processing evaluation.

This measures document routing/OCR success on the checked-in sample set. It does
not claim LLM extraction accuracy because live model credentials and a labeled
field-level benchmark are not part of the repository.
"""
import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/dataset.jsonl")
    parser.add_argument("--output", default="evaluation/results.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "backend"))
    from app.pipelines import process_file

    records = [json.loads(line) for line in (root / args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    results = []
    for record in records:
        path = root / record["path"]
        started = time.perf_counter()
        try:
            doc = process_file(path)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            text = doc.full_text.upper()
            checks = {
                "kind": doc.kind == record["expected_kind"],
                "pages": len(doc.pages) == record["expected_pages"],
                "text": all(token.upper() in text for token in record.get("text_contains", [])),
            }
            results.append({"id": record["id"], "status": doc.status, "elapsed_ms": elapsed_ms,
                            "observed_kind": doc.kind, "observed_pages": len(doc.pages), "checks": checks})
        except Exception as exc:
            results.append({"id": record["id"], "status": "failed",
                            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                            "error": f"{type(exc).__name__}: {exc}"})

    passed = sum(all(item.get("checks", {}).values()) for item in results)
    summary = {"records": len(results), "passed": passed, "failed": len(results) - passed,
               "success_rate": passed / len(results) if results else None, "results": results}
    output = root / args.output
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
