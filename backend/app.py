import os
import google.generativeai as genai
from google.generativeai.protos import FunctionDeclaration, Tool
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import json
import datetime
import subprocess
import chromadb
from sentence_transformers import SentenceTransformer

script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=dotenv_path)

chroma_db_path = os.path.join(script_dir, 'chroma_db')
scratchpad_path = os.path.join(script_dir, 'scratchpad.md')
main_plan_path = os.path.join(script_dir, 'main-plan.md')
raw_conversations_path = os.path.join(script_dir, '../raw-conversations')


app = Flask(__name__)
CORS(app)

# Initialize ChromaDB and Sentence Transformer
client = chromadb.PersistentClient(path=chroma_db_path)
collection = client.get_or_create_collection("codebase")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# Configure the generative AI model
try:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "YOUR_API_KEY":
        print("ERROR: GOOGLE_API_KEY is not set or is a placeholder. Please set it in backend/.env")
    else:
        genai.configure(api_key=api_key)
except Exception as e:
    print(f"An unexpected error occurred during genai.configure: {e}")

# --- Tool Definitions ---
def read_file(filepath: str) -> str:
    """Reads the content of a file."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return str(e)

def write_file(filepath: str, content: str) -> str:
    """Writes content to a file."""
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        return "File written successfully."
    except Exception as e:
        return str(e)

def list_files(path: str) -> str:
    """Lists the files in a directory."""
    try:
        return "\n".join(os.listdir(path))
    except Exception as e:
        return str(e)

tools = [
    FunctionDeclaration(
        name="read_file",
        description="Reads the content of a file.",
        parameters={"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]},
    ),
    FunctionDeclaration(
        name="write_file",
        description="Writes content to a file.",
        parameters={"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}}, "required": ["filepath", "content"]},
    ),
    FunctionDeclaration(
        name="list_files",
        description="Lists the files in a directory.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    ),
]

tool_config = Tool(function_declarations=tools)
tool_map = {
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
}


@app.route('/models', methods=['GET'])
def get_models():
    """Returns a list of available models."""
    try:
        models = [m.name for m in genai.list_models()]
        return jsonify(models)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/index', methods=['POST'])
def index_codebase():
    """Indexes the codebase."""
    try:
        # Clear the collection before indexing
        client.delete_collection("codebase")
        collection = client.get_or_create_collection("codebase")

        for root, dirs, files in os.walk('.'):
            # Skip the .git and backend directories
            if '.git' in dirs:
                dirs.remove('.git')
            if 'backend' in dirs:
                dirs.remove('backend')

            for file in files:
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', errors='ignore') as f:
                        content = f.read()

                    # Chunk the content
                    chunk_size = 1024
                    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]

                    # Generate and store embeddings
                    embeddings = embedding_model.encode(chunks)
                    collection.add(
                        embeddings=embeddings,
                        documents=chunks,
                        metadatas=[{"filepath": filepath} for _ in chunks],
                        ids=[f"{filepath}-{i}" for i in range(len(chunks))]
                    )
                except Exception as e:
                    print(f"Error indexing {filepath}: {e}")

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    """Handles chat messages and returns a response from the AI."""
    data = request.get_json()
    model_name = data.get('model', 'gemini-1.5-flash')
    message = data.get('message')
    conversation_history = data.get('conversation_history', [])

    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
        model = genai.GenerativeModel(model_name, tools=tool_config)

        # Perform semantic search
        query_embedding = embedding_model.encode([message])
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=5
        )

        # Build the prompt with conversation history and search results
        rag_context = "Relevant code snippets:\n"
        for i, doc in enumerate(results['documents'][0]):
            rag_context += f"--- Snippet {i+1} from {results['metadatas'][0][i]['filepath']} ---\n"
            rag_context += f"{doc}\n"

        # Reconstruct the conversation history for the model
        history = []
        for entry in conversation_history:
            history.append({"role": entry['role'], "parts": [{"text": entry['parts'][0]}]})

        # Prepend the RAG context to the user's message
        full_message = f"{rag_context}\n{message}"

        chat_session = model.start_chat(history=history)
        response = chat_session.send_message(full_message)

        while response.function_calls:
            function_call = response.function_calls[0]
            tool_name = function_call.name
            tool_args = {key: value for key, value in function_call.args.items()}

            if tool_name in tool_map:
                tool_result = tool_map[tool_name](**tool_args)
                response = chat_session.send_message(
                    {"role": "function", "parts": [{"function_response": {"name": tool_name, "response": {"result": tool_result}}}]}
                )
            else:
                response = chat_session.send_message(
                    {"role": "function", "parts": [{"function_response": {"name": tool_name, "response": {"result": f"Unknown tool: {tool_name}"}}}]}
                )

        # Save the conversation
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        conversation_file = os.path.join(raw_conversations_path, f'{timestamp}.json')
        os.makedirs(raw_conversations_path, exist_ok=True)
        with open(conversation_file, 'w') as f:
            json.dump({
                "prompt": full_message,
                "response": response.text
            }, f)

        return jsonify({"response": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/scratchpad', methods=['GET', 'POST'])
def scratchpad():
    """Manages the scratchpad."""
    if request.method == 'GET':
        with open(scratchpad_path, 'r') as f:
            return f.read()
    elif request.method == 'POST':
        data = request.get_json()
        with open(scratchpad_path, 'w') as f:
            f.write(data.get('content', ''))
        return jsonify({"status": "success"})

@app.route('/main_plan', methods=['GET', 'POST'])
def main_plan():
    """Manages the main plan."""
    if request.method == 'GET':
        with open(main_plan_path, 'r') as f:
            return f.read()
    elif request.method == 'POST':
        data = request.get_json()
        with open(main_plan_path, 'w') as f:
            f.write(data.get('content', ''))
        return jsonify({"status": "success"})

@app.route('/fix_error', methods=['POST'])
def fix_error():
    """Attempts to fix an error by sending it back to the AI."""
    data = request.get_json()
    model_name = data.get('model', 'gemini-1.5-flash')
    error_message = data.get('error_message')
    conversation_history = data.get('conversation_history', [])

    if not error_message:
        return jsonify({"error": "Error message is required."}), 400

    try:
        model = genai.GenerativeModel(model_name)

        # Reconstruct the conversation history for the model
        history = []
        for entry in conversation_history:
            history.append({"role": entry['role'], "parts": [{"text": entry['parts'][0]}]})

        chat_session = model.start_chat(history=history)
        response = chat_session.send_message(f"The previous response caused an error: {error_message}. Please try again.")

        return jsonify({"response": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Attempting to start Flask server...")
    app.run(debug=True, port=5000)
