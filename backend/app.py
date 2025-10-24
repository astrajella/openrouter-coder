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


app = Flask(__name__)
CORS(app)

# --- Docker Initialization ---
docker_client = docker.from_env()
docker_image = None
auto_approve = False

def build_docker_image():
    global docker_image
    print("Building Docker image...")
    dockerfile_path = os.path.join(project_root)
    docker_image, _ = docker_client.images.build(path=dockerfile_path, dockerfile="Dockerfile.sandbox")
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
from .agent import start_agent_loop, stop_agent_loop, is_agent_running, get_agent_state, provide_confirmation, update_state_manually

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

    start_agent_loop(model_name, goal)
    return jsonify({"status": "Agent started."}), 202


@app.route('/stop_agent', methods=['POST'])
def stop_agent():
    if not is_agent_running():
        return jsonify({"error": "Agent is not running."}), 400

    stop_agent_loop()
    return jsonify({"status": "Agent stopped."})


@app.route('/status', methods=['GET'])
def get_status():
    agent_status_info = get_agent_state()
    return jsonify({
        "main_plan": agent_status_info.get("main_plan"),
        "scratchpad": agent_status_info.get("scratchpad"),
        "agent_running": is_agent_running(),
        "agent_status": agent_status_info.get("status"),
        "confirmation_prompt": agent_status_info.get("confirmation_prompt"),
        "auto_approve": auto_approve
    })

@app.route('/respond_to_confirmation', methods=['POST'])
def handle_confirmation_response():
    data = request.get_json()
    response = data.get('response')
    if not response or response not in ['approve', 'deny']:
        return jsonify({"error": "Invalid response."}), 400

    provide_confirmation(response)
    return jsonify({"status": "Response received."})

@app.route('/toggle_auto_approve', methods=['POST'])
def toggle_auto_approve():
    global auto_approve
    auto_approve = not auto_approve
    return jsonify({"auto_approve": auto_approve})

# --- Model Routes ---
@app.route('/models', methods=['GET'])
def get_models():
    """Returns a list of available models."""
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        return jsonify(models)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- State Persistence Routes ---
@app.route('/update_state', methods=['POST'])
def update_state():
    data = request.get_json()
    new_plan = data.get('main_plan')
    new_scratchpad = data.get('scratchpad')
    update_state_manually(new_plan, new_scratchpad)
    return jsonify({"status": "State updated successfully."})


if __name__ == '__main__':
    build_docker_image()
    print("Attempting to start Flask server...")
    app.run(debug=True, port=5000)
