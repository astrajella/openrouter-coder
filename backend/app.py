import os
import google.generativeai as genai
from google.generativeai.protos import FunctionDeclaration, Tool, Part
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import json
import datetime
import chromadb
from sentence_transformers import SentenceTransformer
import threading

script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=dotenv_path)

chroma_db_path = os.path.join(script_dir, 'chroma_db')
scratchpad_path = os.path.join(script_dir, 'scratchpad.md')
main_plan_path = os.path.join(script_dir, 'main-plan.md')
raw_conversations_path = os.path.join(script_dir, '../raw-conversations')
last_indexed_path = os.path.join(script_dir, 'last_indexed.json')

app = Flask(__name__)
CORS(app)

# Agent state
agent_thread = None
agent_running = False

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

def finish_task() -> str:
    """Signals that the task is complete."""
    global agent_running
    agent_running = False
    return "Task marked as complete. Agent stopped."

tools = [
    FunctionDeclaration(name="read_file", description="Reads the content of a file.", parameters={"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]}),
    FunctionDeclaration(name="write_file", description="Writes content to a file.", parameters={"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}}, "required": ["filepath", "content"]}),
    FunctionDeclaration(name="list_files", description="Lists the files in a directory.", parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    FunctionDeclaration(name="finish_task", description="Signals that the task is complete and stops the agent.", parameters={}),
]

tool_config = Tool(function_declarations=tools)
tool_map = {
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "finish_task": finish_task,
}

# --- Agent Loop ---
def agent_loop(goal: str, model_name: str):
    global agent_running
    agent_running = True

    with open(main_plan_path, 'w') as f:
        f.write(f"Goal: {goal}\n\nPlan:\n- ")

    with open(scratchpad_path, 'w') as f:
        f.write("Scratchpad:\n")

    history = []
    model = genai.GenerativeModel(model_name, tools=tool_config)
    chat_session = model.start_chat(history=history)

    while agent_running:
        with open(main_plan_path, 'r') as f:
            main_plan = f.read()
        with open(scratchpad_path, 'r') as f:
            scratchpad = f.read()

        prompt = f"Main Plan:\n{main_plan}\n\nScratchpad:\n{scratchpad}\n\nBased on the above, what is the next single action to take? Use a tool to proceed."

        response = chat_session.send_message(prompt)

        if not response.function_calls:
            with open(scratchpad_path, 'a') as f:
                f.write(f"\n[AGENT]: {response.text}")
            continue

        function_call = response.function_calls[0]
        tool_name = function_call.name
        tool_args = {key: value for key, value in function_call.args.items()}

        with open(scratchpad_path, 'a') as f:
            f.write(f"\n[ACTION]: Calling tool {tool_name} with args {tool_args}")

        if tool_name in tool_map:
            tool_result = tool_map[tool_name](**tool_args)
            with open(scratchpad_path, 'a') as f:
                f.write(f"\n[TOOL RESULT]: {tool_result}")
        else:
            with open(scratchpad_path, 'a') as f:
                f.write(f"\n[ERROR]: Unknown tool {tool_name}")

@app.route('/execute_plan', methods=['POST'])
def execute_plan():
    global agent_thread, agent_running
    if agent_running:
        return jsonify({"error": "Agent is already running."}), 400

    data = request.get_json()
    goal = data.get('goal')
    model_name = data.get('model', 'gemini-1.5-flash')
    if not goal:
        return jsonify({"error": "Goal is required."}), 400

    agent_thread = threading.Thread(target=agent_loop, args=(goal, model_name))
    agent_thread.start()
    return jsonify({"status": "Agent started."}), 202

@app.route('/stop_agent', methods=['POST'])
def stop_agent():
    global agent_running, agent_thread
    if not agent_running:
        return jsonify({"error": "Agent is not running."}), 400

    agent_running = False
    agent_thread.join()
    return jsonify({"status": "Agent stopped."})

@app.route('/status', methods=['GET'])
def get_status():
    with open(scratchpad_path, 'r') as f:
        scratchpad = f.read()
    with open(main_plan_path, 'r') as f:
        main_plan = f.read()
    return jsonify({"scratchpad": scratchpad, "main_plan": main_plan, "agent_running": agent_running})

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
        last_indexed = {}
        if os.path.exists(last_indexed_path):
            with open(last_indexed_path, 'r') as f:
                last_indexed = json.load(f)

        for root, dirs, files in os.walk('.'):
            if '.git' in dirs: dirs.remove('.git')
            if 'backend' in dirs: dirs.remove('backend')

            for file in files:
                filepath = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(filepath)
                    if filepath in last_indexed and mtime <= last_indexed[filepath]:
                        continue

                    with open(filepath, 'r', errors='ignore') as f:
                        content = f.read()

                    chunks = [content[i:i+1024] for i in range(0, len(content), 1024)]
                    embeddings = embedding_model.encode(chunks)
                    ids = [f"{filepath}-{i}" for i in range(len(chunks))]

                    collection.delete(where={"filepath": filepath})
                    collection.add(embeddings=embeddings, documents=chunks, metadatas=[{"filepath": filepath} for _ in chunks], ids=ids)
                    last_indexed[filepath] = mtime
                except Exception as e:
                    print(f"Error indexing {filepath}: {e}")

        with open(last_indexed_path, 'w') as f:
            json.dump(last_indexed, f)

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def reconstruct_history(conversation_history):
    history = []
    for entry in conversation_history:
        role = entry['role']
        parts = []
        for part in entry['parts']:
            if 'text' in part:
                parts.append(Part(text=part['text']))
            elif 'function_call' in part:
                parts.append(Part(function_call=part['function_call']))
            elif 'function_response' in part:
                parts.append(Part(function_response=part['function_response']))
        history.append({"role": role, "parts": parts})
    return history

def execute_tool_loop(chat_session, history):
    response = chat_session.send_message(history[-1]["parts"])

    while response.function_calls:
        function_call = response.function_calls[0]
        tool_name = function_call.name
        tool_args = {key: value for key, value in function_call.args.items()}

        history.append({"role": "model", "parts": [Part(function_call=function_call)]})

        if tool_name in tool_map:
            tool_result = tool_map[tool_name](**tool_args)
            part = Part(function_response={"name": tool_name, "response": {"result": tool_result}})
            history.append({"role": "tool", "parts": [part]})
            response = chat_session.send_message([part])
        else:
            tool_result = f"Unknown tool: {tool_name}"
            part = Part(function_response={"name": tool_name, "response": {"result": tool_result}})
            history.append({"role": "tool", "parts": [part]})
            response = chat_session.send_message([part])

    history.append({"role": "model", "parts": [Part(text=response.text)]})
    return response, history

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

        query_embedding = embedding_model.encode([message])
        results = collection.query(query_embeddings=query_embedding, n_results=5)

        rag_context = "Relevant code snippets:\n"
        for i, doc in enumerate(results['documents'][0]):
            rag_context += f"--- Snippet {i+1} from {results['metadatas'][0][i]['filepath']} ---\n{doc}\n"

        history = reconstruct_history(conversation_history)
        full_message = f"{rag_context}\n{message}"
        history.append({"role": "user", "parts": [Part(text=full_message)]})

        chat_session = model.start_chat(history=history[:-1])
        response, history = execute_tool_loop(chat_session, history)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        conversation_file = os.path.join(raw_conversations_path, f'{timestamp}.json')
        os.makedirs(raw_conversations_path, exist_ok=True)
        serializable_history = [
            {"role": h["role"], "parts": [{"text": p.text} if p.text else {"function_call": {"name": p.function_call.name, "args": dict(p.function_call.args)}} if p.function_call else {"function_response": {"name": p.function_response.name, "response": dict(p.function_response.response)}} for p in h["parts"]]}
            for h in history
        ]
        with open(conversation_file, 'w') as f:
            json.dump(serializable_history, f)

        return jsonify({"response": response.text, "history": serializable_history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/scratchpad', methods=['GET', 'POST'])
def scratchpad():
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
    data = request.get_json()
    model_name = data.get('model', 'gemini-1.5-flash')
    error_message = data.get('error_message')
    conversation_history = data.get('conversation_history', [])

    if not error_message:
        return jsonify({"error": "Error message is required."}), 400

    try:
        model = genai.GenerativeModel(model_name, tools=tool_config)
        history = reconstruct_history(conversation_history)
        history.append({"role": "user", "parts": [Part(text=f"The previous response caused an error: {error_message}. Please try again.")]})

        chat_session = model.start_chat(history=history[:-1])
        response, history = execute_tool_loop(chat_session, history)

        serializable_history = [
            {"role": h["role"], "parts": [{"text": p.text} if p.text else {"function_call": {"name": p.function_call.name, "args": dict(p.function_call.args)}} if p.function_call else {"function_response": {"name": p.function_response.name, "response": dict(p.function_response.response)}} for p in h["parts"]]}
            for h in history
        ]

        return jsonify({"response": response.text, "history": serializable_history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Attempting to start Flask server...")
    app.run(debug=True, port=5000)
