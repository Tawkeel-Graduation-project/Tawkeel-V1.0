import json

chunks = json.load(open("chunks.json", encoding="utf-8"))

by_number = {c["article_number"]: c for c in chunks}
print(len(chunks))
print(json.dumps(by_number[30], ensure_ascii=False, indent=2))
print(by_number[41]["text"][-100:])