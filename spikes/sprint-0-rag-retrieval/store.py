import json
import numpy as np
from dotenv import load_dotenv

load_dotenv()

chunks = json.load(open("chunks.json", encoding="utf-8"))
vectors = np.array(json.load(open("vectors.json")))      # shape: (39, 3072)

# Scale every vector to length 1, so cosine similarity = a plain dot product
vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

def search(query_vec, k=3):
    q = np.array(query_vec)
    q = q / np.linalg.norm(q)
    scores = vectors @ q                      # 39 scores, one per article
    top = np.argsort(scores)[::-1][:k]        # positions of the k highest
    return [(chunks[i], float(scores[i])) for i in top]

if __name__ == "__main__":
    print(vectors.shape)
    for chunk, score in search(vectors[5], k=3):
        print(chunk["article_number"], round(score, 3))