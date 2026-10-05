import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from store import search

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

QUESTION = """اشتريت جهاز من محل ولما روَّحت البيت غيرت رأيي وحسيت إني مش محتاجه، رغم إن مفيش فيه أي عيب. هل القانون بيديني الحق أرجعه واخد فلوسي تاني لو البياع قالي مفيش ترجيع؟
"""

r = client.models.embed_content(
    model="gemini-embedding-001",
    contents=QUESTION,
    config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
)
q_vec = r.embeddings[0].values

for chunk, score in search(q_vec, k=5):
    print(chunk["article_number"], round(score, 3), chunk["text"][:80])