"""Validate a document OR a saved extraction.

  python try_validate.py extraction.json              (offline: no OpenAI call, instant)
  python try_validate.py "samples/<file>"             (full chain: process -> extract -> validate)
"""
import json
import sys

from app.validation.validator import validate_invoice

arg = sys.argv[1]
source_text = None
if arg.lower().endswith(".json"):
    with open(arg, encoding="utf-8") as f:
        extraction = json.load(f)
else:
    from app.extraction.extractor import ExtractionError, build_source_text, extract_from_document
    from app.extraction.llm import OpenAIClient
    from app.pipelines import ProcessingError, process_file
    try:
        doc = process_file(arg)
        source_text = build_source_text(doc)
        extraction = extract_from_document(doc, OpenAIClient())
    except (ProcessingError, ExtractionError) as e:
        print(f"FAILED [{getattr(e, 'code', 'error')}]: {e}")
        sys.exit(1)
    with open("extraction.json", "w", encoding="utf-8") as f:
        json.dump(extraction, f, indent=2, ensure_ascii=False)

report = validate_invoice(extraction, source_text=source_text).to_dict()
print(f"STATUS: {report['status'].upper()}   {report['counts']}")
for i in report["issues"]:
    print(f"  [{i['severity']:<7}] {i['rule']:<32} {i['message']}")
with open("validation.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
