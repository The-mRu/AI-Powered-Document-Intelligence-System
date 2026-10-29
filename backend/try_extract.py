"""python try_extract.py samples/<file>  -> runs Task 1 then Task 2 and prints JSON."""
import json
import sys

from app.extraction.extractor import ExtractionError, extract_from_document
from app.extraction.llm import OpenAIClient
from app.pipelines import ProcessingError, process_file

try:
    doc = process_file(sys.argv[1])
    result = extract_from_document(doc, OpenAIClient())
except (ProcessingError, ExtractionError) as e:
    print(f"FAILED [{getattr(e, 'code', 'error')}]: {e}")
    sys.exit(1)

print(json.dumps(result, indent=2, ensure_ascii=False))
with open("extraction.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

# docker run --rm --env-file .env -v ${PWD}:/code docintel python try_extract.py "samples/Standard Grocery Bill.jpg"
# docker run --rm --env-file .env -v ${PWD}:/code docintel python try_extract.py samples/invoice-sample.pdf

