# backend/app.py

import os
import google.generativeai as genai
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from dotenv import load_dotenv
import json
import datetime
import docker

# --- Pathing and Initialization ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

dotenv_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=dotenv_path)

scratchpad_path = os.path.join(project_root, 'backend', 'scratchpad.md')
main_plan_path = os.path.join(project_root, 'backend', 'main-plan.md')
raw_conversations_path = os.path.join(project_root, 'raw-conversations')
last_indexed_path = os.path.join(project_root, 'backend', 'last_indexed.json')

app = Flask(__name__)
CORS(app)

# --- Docker Initialization ---
docker_client = docker.from_env()
docker_image = None

def build_docker_image():
    global docker_image
    print("Building Docker image...")
    dockerfile_path = os.path.join(project_root, 'backend')
    docker_image, _ = docker_client.images.build(path=dockerfile_path, dockerfile="Dockerfile")
    print("Docker image built.")

# --- Google AI Initialization ---
try:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "YOUR_API_KEY":
        print("ERROR: GOOGLE_API_KEY is not set or is a placeholder. Please set it in backend/.env")
    else:
        genai.configure(api_key=api_key)
except Exception as e:
    print(f"An unexpected error occurred during genai.configure: {e}")

# --- Module Imports ---
from .tools import tool_config
from .agent import start_agent_loop, stop_agent_loop, is_agent_running
from .rag import index_codebase, query_codebase
from .gemma import reconstruct_history, handle_tool_calls, stream_chat_response, serializable_history

# --- Agent Routes ---
@app.route('/execute_plan', methods=['POST'])
def execute_plan():
    if is_agent_running():
        return jsonify({"error": "Agent is already running."}), 400

    data = request.get_json()
    goal = data.get('goal')
    model_name = data.get('model', 'gemini-1.5-flash')
    if not goal:
        return jsonify({"error": "Goal is required."}), 400

    if start_agent_loop(goal, model_name):
        return jsonify({"status": "Agent started."}), 202
    else:
        return jsonify({"error": "Failed to start agent."}), 500

@app.route('/stop_agent', methods=['POST'])
def stop_agent():
    if not is_agent_running():
        return jsonify({"error": "Agent is not running."}), 400

    if stop_agent_loop():
        return jsonify({"status": "Agent stopped."})
    else:
        return jsonify({"error": "Failed to stop agent."}), 500

@app.route('/status', methods=['GET'])
def get_status():
    try:
        with open(scratchpad_path, 'r') as f:
            scratchpad = f.read()
    except FileNotFoundError:
        scratchpad = ""
    try:
        with open(main_plan_path, 'r') as f:
            main_plan = f.read()
    except FileNotFoundError:
        main_plan = ""
    return jsonify({"scratchpad": scratchpad, "main_plan": main_plan, "agent_running": is_agent_running()})

# --- Model and RAG Routes ---
@app.route('/models', methods=['GET'])
def get_models():
    """Returns a list of available models."""
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        return jsonify(models)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/index', methods=['POST'])
def index_codebase_route():
    result = index_codebase()
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

# --- Chat Routes ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    model_name = data.get('model', 'gemini-1.5-flash')
    message = data.get('message')
    conversation_history = data.get('conversation_history', [])

    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
        model = genai.GenerativeModel(model_name, tools=tool_config)

        rag_context = query_codebase(message)

        history = reconstruct_history(conversation_history)
        full_message = f"{rag_context}\\n\\nUser Question: {message}"
        history.append({"role": "user", "parts": [genai.protos.Part(text=full_message)]})

        chat_session = model.start_chat(history=history[:-1])

        # Handle tool calls first (non-streaming)
        history_with_tool_calls = handle_tool_calls(chat_session, history)

        # Now, create the generator for the streaming response
        response_generator = stream_chat_response(chat_session, history_with_tool_calls)

        # Before streaming, save the complete history
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        conversation_file = os.path.join(raw_conversations_path, f'{timestamp}.json')
        os.makedirs(raw_conversations_path, exist_ok=True)
        with open(conversation_file, 'w') as f:
            json.dump(serializable_history(history_with_tool_calls), f, indent=2)

        return Response(response_generator, mimetype='text/event-stream')

    except Exception as e:
        # This will catch errors during the initial setup, but not during the stream itself
        return jsonify({"error": str(e)}), 500


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
        history.append({"role": "user", "parts": [genai.protos.Part(text=f"The previous response caused an error: {error_message}. Please analyze the conversation and the error, then provide a corrected response or code.")]})

        chat_session = model.start_chat(history=history[:-1])
        history_with_tool_calls = handle_tool_calls(chat_session, history)
        response_generator = stream_chat_response(chat_session, history_with_tool_calls)

        return Response(response_generator, mimetype='text/event-stream')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- State Persistence Routes ---
@app.route('/scratchpad', methods=['GET', 'POST'])
def scratchpad():
    if request.method == 'GET':
        try:
            with open(scratchpad_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return ""
    elif request.method == 'POST':
        data = request.get_json()
        with open(scratchpad_path, 'w') as f:
            f.write(data.get('content', ''))
        return jsonify({"status": "success"})

@app.route('/main_plan', methods=['GET', 'POST'])
def main_plan():
    if request.method == 'GET':
        try:
            with open(main_plan_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return ""
    elif request.method == 'POST':
        data = request.get_json()
        with open(main_plan_path, 'w') as f:
            f.write(data.get('content', ''))
        return jsonify({"status": "success"})

if __name__ == '__main__':
    build_docker_image()
    print("Attempting to start Flask server...")
    app.run(debug=True, port=5000)
