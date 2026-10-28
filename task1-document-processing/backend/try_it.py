import sys
from app.pipelines import process_file

doc = process_file(sys.argv[1])
print("status:", doc.status, "| warnings:", doc.warnings)
with open("out.txt", "w", encoding="utf-8") as f:
    for p in doc.pages:
        header = f"--- page {p.page_no} ({p.method}, confidence={p.confidence}, {p.duration_ms}ms) ---"
        print(header)
        f.write(header + "\n" + p.text + "\n")
print("full text saved to out.txt")