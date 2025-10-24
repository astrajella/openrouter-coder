import os
import google.generativeai as genai
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import json
import datetime
import subprocess

script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=dotenv_path)

scratchpad_path = os.path.join(script_dir, 'scratchpad.md')
main_plan_path = os.path.join(script_dir, 'main-plan.md')
raw_conversations_path = os.path.join(script_dir, '../raw-conversations')


app = Flask(__name__)
CORS(app)

# Configure the generative AI model
try:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "YOUR_API_KEY":
        print("ERROR: GOOGLE_API_KEY is not set or is a placeholder. Please set it in backend/.env")
    else:
        genai.configure(api_key=api_key)
except Exception as e:
    print(f"An unexpected error occurred during genai.configure: {e}")

@app.route('/models', methods=['GET'])
def get_models():
    """Returns a list of available models."""
    try:
        models = [m.name for m in genai.list_models()]
        return jsonify(models)
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
        model = genai.GenerativeModel(model_name)

        # Build the prompt with conversation history and tools
        prompt = ""
        for entry in conversation_history:
            prompt += f"{entry['role']}: {entry['parts'][0]}\n"
        prompt += f"user: {message}\n"
        prompt += """
You have the following tools available:
- `read_file(filepath)`: Reads the content of a file.
- `write_file(filepath, content)`: Writes content to a file.
- `list_files(path)`: Lists the files in a directory.
- `execute_bash(command)`: Executes a bash command.

To use a tool, respond with a JSON object with the following format:
{"tool": "tool_name", "args": {"arg1": "value1", "arg2": "value2"}}
"""

        response = model.generate_content(prompt)

        # Check if the model wants to use a tool
        try:
            tool_call = json.loads(response.text)
            if "tool" in tool_call and "args" in tool_call:
                tool_name = tool_call["tool"]
                tool_args = tool_call["args"]

                if tool_name == "read_file":
                    result = read_file(tool_args["filepath"])
                elif tool_name == "write_file":
                    result = write_file(tool_args["filepath"], tool_args["content"])
                elif tool_name == "list_files":
                    result = list_files(tool_args["path"])
                elif tool_name == "execute_bash":
                    result = execute_bash(tool_args["command"])
                else:
                    result = f"Unknown tool: {tool_name}"

                return jsonify({"tool_result": result})
        except (json.JSONDecodeError, KeyError):
            # Not a tool call, just a regular response
            pass

        # Save the conversation
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        conversation_file = os.path.join(raw_conversations_path, f'{timestamp}.json')
        os.makedirs(raw_conversations_path, exist_ok=True)
        with open(conversation_file, 'w') as f:
            json.dump({
                "prompt": prompt,
                "response": response.text
            }, f)

        return jsonify({"response": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def read_file(filepath):
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return str(e)

def write_file(filepath, content):
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        return "File written successfully."
    except Exception as e:
        return str(e)

def list_files(path):
    try:
        return "\n".join(os.listdir(path))
    except Exception as e:
        return str(e)

def execute_bash(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    except Exception as e:
        return str(e)

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

        prompt = ""
        for entry in conversation_history:
            prompt += f"{entry['role']}: {entry['parts'][0]}\n"
        prompt += f"The previous response caused an error: {error_message}. Please try again.\n"

        response = model.generate_content(prompt)

        return jsonify({"response": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Attempting to start Flask server...")
    app.run(debug=True, port=5000)
