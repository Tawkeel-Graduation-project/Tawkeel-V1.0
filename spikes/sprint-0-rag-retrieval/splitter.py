import re, json

PATH = "consumer_protection_181_2018_part2.txt"
lines = [l.strip() for l in open(PATH, encoding="utf-8").read().splitlines()]
lines = [l for l in lines if l]            # drop blank lines

chunks = []
part, chapter = "", ""
current = None

i = 0
while i < len(lines):
    line = lines[i]
    article = re.match(r"^مادة \((\d+)\)\s*:", line)

    if line.startswith("الباب"):
        part = f"{line}: {lines[i + 1]}"       # keyword line + title line
        i += 2
    elif re.match(r"^\(?الفصل", line):
        chapter = f"{line}: {lines[i + 1]}"
        i += 2
    elif article:
        current = {"part": part, "chapter": chapter,
                   "article_number": int(article.group(1)), "text": ""}
        chunks.append(current)
        i += 1
    else:
        current["text"] += line + "\n"          # belongs to the current article
        i += 1

for c in chunks:
    c["text"] = c["text"].strip()

json.dump(chunks, open("chunks.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)       # ensure_ascii=False keeps Arabic readable