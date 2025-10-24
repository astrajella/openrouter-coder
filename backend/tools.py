# backend/tools.py

import os
import docker
from google.generativeai.protos import FunctionDeclaration, Tool, Schema, Type
import requests
import json
import datetime
import google.generativeai as genai

# --- Pathing and Safeguards ---
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
knowledge_base_path = os.path.join(project_root, 'backend', 'knowledge_base.md')
workspace_path = os.path.join(project_root, 'workspace')

PROTECTED_PATHS = [
    os.path.normpath(os.path.join(project_root, 'backend')),
    os.path.normpath(os.path.join(project_root, 'frontend')),
    os.path.normpath(os.path.join(project_root, 'tests')),
    os.path.normpath(os.path.join(project_root, 'docker-compose.yml')),
    os.path.normpath(os.path.join(project_root, 'Dockerfile.sandbox')),
    os.path.normpath(os.path.join(project_root, 'setup.sh')),
    os.path.normpath(os.path.join(project_root, 'requirements.txt')),
]

def is_protected(path: str) -> bool:
    """Checks if a path is within a protected directory."""
    normalized_path = os.path.normpath(path)
    for protected in PROTECTED_PATHS:
        if os.path.commonpath([normalized_path, protected]) == protected:
            return True
    return False

def get_safe_path(filepath: str) -> str:
    """Joins the provided path with the project root and normalizes it."""
    return os.path.normpath(os.path.join(project_root, filepath))

# --- Tool Definitions ---

def read_file(filepath: str) -> str:
    """Reads the content of a file."""
    try:
        safe_path = get_safe_path(filepath)
        with open(safe_path, 'r') as f:
            return f.read()
    except Exception as e:
        return str(e)

def write_file(filepath: str, content: str) -> str:
    """Writes content to a file, if not protected."""
    safe_path = get_safe_path(filepath)
    if is_protected(safe_path):
        return "Error: Permission Denied. Cannot write to a protected system file."
    try:
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, 'w') as f:
            f.write(content)
        return "File written successfully."
    except Exception as e:
        return str(e)

def list_files(path: str) -> str:
    """Lists the files in a directory recursively and returns a JSON tree."""
    try:
        safe_path = get_safe_path(path)
        tree = {}
        for root, dirs, files in os.walk(safe_path):
            current_level = tree
            rel_path = os.path.relpath(root, safe_path)
            if rel_path != ".":
                for part in rel_path.split(os.sep):
                    current_level = current_level.setdefault(part, {})

            for d in dirs:
                current_level.setdefault(d, {})
            for f in files:
                current_level[f] = None

        return json.dumps(tree, indent=2)

    except Exception as e:
        return str(e)

def create_directory(path: str) -> str:
    """Creates a new directory, if not protected."""
    safe_path = get_safe_path(path)
    if is_protected(safe_path):
        return "Error: Permission Denied. Cannot create a directory in a protected location."
    try:
        os.makedirs(safe_path, exist_ok=True)
        return f"Directory '{path}' created successfully."
    except Exception as e:
        return str(e)

def delete_file(filepath: str) -> str:
    """Deletes a file, if not protected."""
    safe_path = get_safe_path(filepath)
    if is_protected(safe_path):
        return "Error: Permission Denied. Cannot delete a protected system file."
    try:
        os.remove(safe_path)
        return f"File '{filepath}' deleted successfully."
    except Exception as e:
        return str(e)

def rename_file(old_filepath: str, new_filepath: str) -> str:
    """Renames or moves a file or directory, if not protected."""
    safe_old_path = get_safe_path(old_filepath)
    safe_new_path = get_safe_path(new_filepath)
    if is_protected(safe_old_path) or is_protected(safe_new_path):
        return "Error: Permission Denied. Cannot rename or move protected system files."
    try:
        os.rename(safe_old_path, safe_new_path)
        return f"'{old_filepath}' renamed to '{new_filepath}' successfully."
    except Exception as e:
        return str(e)

def execute_python_code(code: str) -> str:
    """Executes Python code in a sandboxed Docker container."""
    from .app import docker_image, docker_client
    if not docker_image:
        return "Docker image not built yet. Please wait."

    temp_code_path = os.path.join(workspace_path, "temp_code.py")
    try:
        with open(temp_code_path, "w") as f:
            f.write(code)

        container = docker_client.containers.run(
            docker_image.id,
            volumes={os.path.abspath(temp_code_path): {'bind': '/app/temp_code.py', 'mode': 'ro'}},
            detach=True
        )
        container.wait()
        logs = container.logs()
        container.remove()

        return logs.decode('utf-8')
    except Exception as e:
        return str(e)
    finally:
        if os.path.exists(temp_code_path):
            os.remove(temp_code_path)

def web_search(query: str) -> str:
    """Performs a web search using the Tavily API."""
    try:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return "Error: TAVILY_API_KEY is not set."

        response = requests.post("https://api.tavily.com/search", json={
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "include_answer": True,
            "max_results": 5
        })
        response.raise_for_status()
        return json.dumps(response.json())
    except Exception as e:
        return str(e)

def record_learning(learning: str) -> str:
    """Records a key learning or insight to the agent's long-term knowledge base."""
    try:
        with open(knowledge_base_path, 'a') as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n---\n**Learning recorded at {timestamp}:**\n{learning}\n")
        return "Learning recorded successfully."
    except Exception as e:
        return str(e)

def request_confirmation(prompt: str) -> str:
    """Requests user confirmation before proceeding with a critical action."""
    from .app import auto_approve
    if auto_approve:
        return "Auto-approved."
    from .agent import pause_for_confirmation
    return pause_for_confirmation(prompt)

def generate_project_blueprint(target_directory: str) -> str:
    """Analyzes a directory and generates a high-level project blueprint."""
    safe_path = get_safe_path(target_directory)
    if not os.path.normpath(safe_path).startswith(os.path.normpath(workspace_path)):
        return "Error: Can only generate a blueprint for a directory within the workspace."

    try:
        aggregated_content = ""
        file_tree = ""
        for root, dirs, files in os.walk(safe_path):
            # Exclude common non-source directories
            dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', '.git']]

            relative_root = os.path.relpath(root, safe_path)
            if relative_root == '.':
                relative_root = ''

            for name in dirs:
                file_tree += f"{relative_root}/{name}/\n"
            for name in files:
                file_tree += f"{relative_root}/{name}\n"
                try:
                    with open(os.path.join(root, name), 'r', errors='ignore') as f:
                        aggregated_content += f"--- FILE: {relative_root}/{name} ---\n{f.read()}\n\n"
                except Exception:
                    continue

        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            f"Analyze the following codebase, summarized below, and generate a concise 'Project Blueprint'. "
            f"Describe the overall architecture, the purpose of each key component/directory, and how they interact. "
            f"Focus on data flow, state management, and the main business logic.\n\n"
            f"File Tree:\n{file_tree}\n\n"
            f"Aggregated Content:\n{aggregated_content}"
        )

        blueprint = response.text
        record_learning(f"Project Blueprint for {target_directory}:\n{blueprint}")
        return f"Project blueprint generated and saved to knowledge base."

    except Exception as e:
        return f"Error generating project blueprint: {e}"

def finish_task() -> str:
    """Signals that the task is complete."""
    from .agent import stop_agent_loop
    stop_agent_loop()
    return "Task marked as complete. Agent stopped."


# --- Tool Configuration ---
tools = [
    FunctionDeclaration(name="read_file", description="Reads the content of a file.", parameters=Schema(type=Type.OBJECT, properties={"filepath": Schema(type=Type.STRING)}, required=["filepath"])),
    FunctionDeclaration(name="write_file", description="Writes content to a file in the workspace.", parameters=Schema(type=Type.OBJECT, properties={"filepath": Schema(type=Type.STRING), "content": Schema(type=Type.STRING)}, required=["filepath", "content"])),
    FunctionDeclaration(name="list_files", description="Lists the files in a directory recursively.", parameters=Schema(type=Type.OBJECT, properties={"path": Schema(type=Type.STRING)}, required=["path"])),
    FunctionDeclaration(name="create_directory", description="Creates a new directory in the workspace.", parameters=Schema(type=Type.OBJECT, properties={"path": Schema(type=Type.STRING)}, required=["path"])),
    FunctionDeclaration(name="delete_file", description="Deletes a file in the workspace.", parameters=Schema(type=Type.OBJECT, properties={"filepath": Schema(type=Type.STRING)}, required=["filepath"])),
    FunctionDeclaration(name="rename_file", description="Renames or moves a file in the workspace.", parameters=Schema(type=Type.OBJECT, properties={"old_filepath": Schema(type=Type.STRING), "new_filepath": Schema(type=Type.STRING)}, required=["old_filepath", "new_filepath"])),
    FunctionDeclaration(name="execute_python_code", description="Executes Python code in a sandboxed Docker container.", parameters=Schema(type=Type.OBJECT, properties={"code": Schema(type=Type.STRING)}, required=["code"])),
    FunctionDeclaration(name="web_search", description="Performs a web search.", parameters=Schema(type=Type.OBJECT, properties={"query": Schema(type=Type.STRING)}, required=["query"])),
    FunctionDeclaration(name="record_learning", description="Records a key learning to the agent's long-term knowledge base.", parameters=Schema(type=Type.OBJECT, properties={"learning": Schema(type=Type.STRING)}, required=["learning"])),
    FunctionDeclaration(name="request_confirmation", description="Asks the user for confirmation before a critical action.", parameters=Schema(type=Type.OBJECT, properties={"prompt": Schema(type=Type.STRING)}, required=["prompt"])),
    FunctionDeclaration(name="generate_project_blueprint", description="Analyzes a directory to generate a high-level project blueprint.", parameters=Schema(type=Type.OBJECT, properties={"target_directory": Schema(type=Type.STRING)}, required=["target_directory"])),
    FunctionDeclaration(name="finish_task", description="Signals that the task is complete.", parameters=Schema(type=Type.OBJECT, properties={})),
]

tool_config = Tool(function_declarations=tools)
tool_map = {
    "read_file": read_file, "write_file": write_file, "list_files": list_files, "create_directory": create_directory, "delete_file": delete_file, "rename_file": rename_file, "execute_python_code": execute_python_code, "web_search": web_search, "record_learning": record_learning, "request_confirmation": request_confirmation, "generate_project_blueprint": generate_project_blueprint, "finish_task": finish_task,
}
