# backend/tools.py

import os
import docker
from google.generativeai.protos import FunctionDeclaration, Tool
import requests
import json

# --- Pathing ---
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    """Writes content to a file."""
    try:
        safe_path = get_safe_path(filepath)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, 'w') as f:
            f.write(content)
        return "File written successfully."
    except Exception as e:
        return str(e)

def list_files(path: str) -> str:
    """Lists the files in a directory."""
    try:
        safe_path = get_safe_path(path)
        return "\n".join(os.listdir(safe_path))
    except Exception as e:
        return str(e)

def execute_python_code(code: str) -> str:
    """Executes Python code in a sandboxed Docker container."""
    from .app import docker_image, docker_client
    if not docker_image:
        return "Docker image not built yet. Please wait."

    temp_code_path = os.path.join(project_root, "temp_code.py")
    try:
        with open(temp_code_path, "w") as f:
            f.write(code)

        container = docker_client.containers.run(
            docker_image.id,
            volumes={temp_code_path: {'bind': '/app/temp_code.py', 'mode': 'ro'}},
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

def finish_task() -> str:
    """Signals that the task is complete."""
    from .agent import stop_agent_loop
    stop_agent_loop()
    return "Task marked as complete. Agent stopped."

# --- Tool Configuration ---
tools = [
    FunctionDeclaration(name="read_file", description="Reads the content of a file.", parameters={"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]}),
    FunctionDeclaration(name="write_file", description="Writes content to a file.", parameters={"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}}, "required": ["filepath", "content"]}),
    FunctionDeclaration(name="list_files", description="Lists the files in a directory.", parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    FunctionDeclaration(name="execute_python_code", description="Executes Python code in a sandboxed Docker container.", parameters={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}),
    FunctionDeclaration(name="web_search", description="Performs a web search to find information on a topic.", parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    FunctionDeclaration(name="finish_task", description="Signals that the task is complete and stops the agent.", parameters={}),
]

tool_config = Tool(function_declarations=tools)
tool_map = {
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "execute_python_code": execute_python_code,
    "web_search": web_search,
    "finish_task": finish_task,
}
