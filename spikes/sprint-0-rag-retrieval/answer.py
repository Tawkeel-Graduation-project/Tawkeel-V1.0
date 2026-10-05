import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from store import search

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

QUESTION = """اشتريت جهاز من محل ولما روَّحت البيت غيرت رأيي وحسيت إني مش محتاجه، رغم إن مفيش فيه أي عيب. هل القانون بيديني الحق أرجعه واخد فلوسي تاني لو البياع قالي مفيش ترجيع؟
"""
GEN_MODEL = "gemini-3.8-flash"

# 1) retrieve
r = client.models.embed_content(
    model="gemini-embedding-001",
    contents=QUESTION,
    config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
)
hits = search(r.embeddings[0].values, k=3)

# 2) label each article with its number
context = "\n\n".join(f"[مادة {c['article_number']}]\n{c['text']}" for c, _ in hits)

prompt = f"""You are a legal research assistant for Egyptian consumer protection law.
Answer the question using ONLY the articles below.
Cite the article number for every claim, in the form (مادة 17).
If the articles do not contain the answer, say you could not find it.
Do not use outside knowledge. Answer in Arabic.

Articles:
{context}

Question: {QUESTION}"""

resp = client.models.generate_content(model=GEN_MODEL, contents=prompt)

with open("answer.md", "w", encoding="utf-8") as f:
    f.write("## Retrieved\n")
    for c, s in hits:
        f.write(f"- article {c['article_number']} (score {s:.3f})\n")
    f.write("\n## Answer\n" + resp.text + "\n")
print("saved answer.md")