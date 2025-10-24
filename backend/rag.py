# backend/rag.py

import os
import json
import chromadb
from sentence_transformers import SentenceTransformer
from .app import project_root, last_indexed_path

# Initialize ChromaDB and Sentence Transformer
# The host 'chroma' is the service name defined in docker-compose.yml
client = chromadb.HttpClient(host='chroma', port=8000)
collection = client.get_or_create_collection("codebase")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def index_codebase():
    """Indexes the codebase."""
    try:
        last_indexed = {}
        if os.path.exists(last_indexed_path):
            with open(last_indexed_path, 'r') as f:
                last_indexed = json.load(f)

        # Handle deletions
        indexed_files = set(last_indexed.keys())
        current_files = set()
        for root, dirs, files in os.walk(project_root):
            if '.git' in dirs: dirs.remove('.git')
            if 'backend' in dirs: dirs.remove('backend')
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), project_root)
                current_files.add(rel_path)

        deleted_files = indexed_files - current_files
        if deleted_files:
            collection.delete(where={"filepath": {"$in": list(deleted_files)}})
            for filepath in deleted_files:
                del last_indexed[filepath]

        for root, dirs, files in os.walk(project_root):
            if '.git' in dirs: dirs.remove('.git')
            if 'backend' in dirs: dirs.remove('backend')

            for file in files:
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, project_root)
                try:
                    mtime = os.path.getmtime(filepath)
                    if rel_path in last_indexed and mtime <= last_indexed[rel_path]:
                        continue

                    with open(filepath, 'r', errors='ignore') as f:
                        content = f.read()

                    chunks = [content[i:i+1024] for i in range(0, len(content), 1024)]
                    embeddings = embedding_model.encode(chunks)
                    ids = [f"{rel_path}-{i}" for i in range(len(chunks))]

                    collection.delete(where={"filepath": rel_path})
                    collection.add(embeddings=embeddings, documents=chunks, metadatas=[{"filepath": rel_path} for _ in chunks], ids=ids)
                    last_indexed[rel_path] = mtime
                except Exception as e:
                    print(f"Error indexing {filepath}: {e}")

        with open(last_indexed_path, 'w') as f:
            json.dump(last_indexed, f)

        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

def query_codebase(message: str, n_results: int = 5):
    """Queries the codebase for relevant snippets."""
    query_embedding = embedding_model.encode([message])
    results = collection.query(query_embeddings=[query_embedding.tolist()], n_results=n_results)

    rag_context = "Relevant code snippets:\\n"
    if results['documents']:
        for i, doc in enumerate(results['documents'][0]):
            rag_context += f"--- Snippet {i+1} from {results['metadatas'][0][i]['filepath']} ---\\n{doc}\\n"
    return rag_context
