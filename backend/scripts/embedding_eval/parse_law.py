"""Split pasted Arabic law text into one record per article (JSONL).

Usage:
    python parse_law.py labor_law.txt "قانون العمل رقم 12 لسنة 2003" out.jsonl

Each output line: {"id", "source_name", "article_number", "heading", "text"}
"""
import json
import re
import sys

ART_RE = re.compile(r"^\s*المادة\s+(\d+)\s*$")  # "المادة 47" alone on its line
LEVELS = {"الكتاب": 0, "الباب": 1, "الفصل": 2}
DIACRITICS = re.compile(r"[\u064B-\u0652\u0670\u0640]")  # tashkeel + tatweel


def normalize(text: str) -> str:
    """Light Arabic normalization. Apply identically to passages and queries."""
    text = DIACRITICS.sub("", text)
    text = re.sub("[إأآ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", text).strip()


def finalize(raw: str, law_name: str) -> list[dict]:
    """Second pass: collect all versions per key, keep the longest, warn on conflicts."""
    versions: dict[str, list[dict]] = {}
    headings: list[str] = []
    in_code = False
    current = None
    for line in raw.splitlines():
        line = line.strip()
        if not line or line == ".":
            continue
        first_word = line.split()[0]
        if first_word in LEVELS:
            if first_word == "الكتاب":
                in_code = True
            headings = headings[: LEVELS[first_word]] + [line]
            current = None
            continue
        m = ART_RE.match(line)
        if m:
            num = m.group(1)
            current = {
                "id": num if in_code else f"issuance-{num}",
                "source_name": law_name if in_code else f"{law_name} (مواد الإصدار)",
                "article_number": num,
                "heading": " | ".join(headings),
                "lines": [],
            }
            versions.setdefault(current["id"], []).append(current)
            continue
        if current is not None:
            current["lines"].append(line)

    out = []
    for key, vs in versions.items():
        for v in vs:
            v["text"] = "\n".join(v.pop("lines"))
        texts = {v["text"] for v in vs}
        if len(texts) > 1:
            print(f"WARNING: article {key} appears with DIFFERENT texts; keeping the longest")
        best = max(vs, key=lambda v: len(v["text"]))
        if best["text"]:
            out.append(best)
        else:
            print(f"WARNING: article {key} has empty text, skipped")
    return out


def main(path: str, law_name: str, out_path: str) -> None:
    with open(path, encoding="utf-8") as f:
        records = finalize(f.read(), law_name)

    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    code_nums = sorted(int(r["article_number"]) for r in records if not r["id"].startswith("issuance"))
    print(f"{len(records)} records written to {out_path}")
    if code_nums:
        missing = sorted(set(range(code_nums[0], code_nums[-1] + 1)) - set(code_nums))
        print(f"Code articles: {code_nums[0]}..{code_nums[-1]} ({len(code_nums)} found)")
        print(f"Missing numbers in that range: {missing or 'none'}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])