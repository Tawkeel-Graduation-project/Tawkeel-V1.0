import json, os, time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
chunks = json.load(open("chunks.json", encoding="utf-8"))

vectors = []
for c in chunks:
    r = client.models.embed_content(
        model="gemini-embedding-001",
        contents=c["text"],
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    vectors.append(r.embeddings[0].values)
    print("done article", c["article_number"])
    time.sleep(1)         

json.dump(vectors, open("vectors.json", "w"))
print(len(vectors), len(vectors[0]))