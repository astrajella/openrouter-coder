# backend/agent.py

import threading
import google.generativeai as genai
from .tools import tool_config, tool_map
from .app import main_plan_path, scratchpad_path

agent_thread = None
agent_running = False
agent_status = "Idle"
confirmation_event = threading.Event()
confirmation_prompt = ""
user_response = ""

def agent_loop(goal: str, model_name: str):
    global agent_running, agent_status
    agent_running = True
    agent_status = "Starting..."

    with open(main_plan_path, 'w') as f:
        f.write(f"Goal: {goal}\\n\\nPlan:\\n- ")

    with open(scratchpad_path, 'w') as f:
        f.write("Scratchpad:\\n")

    model = genai.GenerativeModel(model_name, tools=tool_config)
    chat_session = model.start_chat(history=[])

    while agent_running:
        agent_status = "Thinking..."
        with open(main_plan_path, 'r') as f:
            main_plan = f.read()
        with open(scratchpad_path, 'r') as f:
            scratchpad = f.read()

        prompt = (
            f"You are an autonomous AI coder. Your current goal is to: {goal}\n\n"
            "**IMPORTANT RULES & GUIDELINES**:\n"
            "1. **Workspace**: You MUST perform all file system operations exclusively within the `/workspace` directory.\n"
            "2. **Confirmation**: Before executing any critical action (like `write_file`, `delete_file`, `rename_file`, `execute_python_code`, or `execute_git_command` with `push`), you MUST use the `request_confirmation` tool.\n"
            "3. **Blueprint**: For complex tasks, consider using the `generate_project_blueprint` tool at the beginning to understand the architecture.\n"
            "4. **Git Workflow**: You MUST follow a standard Git workflow:\n"
            "    a. Create a new branch for your task: `git branch <branch-name>`.\n"
            "    b. Stage your changes: `git add <file-path>`.\n"
            "    c. Commit your changes with a descriptive message: `git commit -m \"Your message\"`.\n"
            "    d. Before finishing, push your branch to the remote: `git push origin <branch-name>`.\n\n"
            f"Here is your main plan:\n{main_plan}\n\n"
            f"Here is your scratchpad with recent actions and results:\n{scratchpad}\n\n"
            "Based on the above, what is the next single action to take? "
            "If the goal is complete, ensure you have pushed your changes, then `record_learning` and `finish_task`."
        )

        response = chat_session.send_message(prompt)

        if not hasattr(response, 'function_calls') or not response.function_calls:
            agent_status = "Responding..."
            with open(scratchpad_path, 'a') as f:
                f.write(f"\\n[AGENT]: {response.text}")
            continue

        for function_call in response.function_calls:
            tool_name = function_call.name
            tool_args = {key: value for key, value in function_call.args.items()}

            agent_status = f"Executing tool: {tool_name}"
            with open(scratchpad_path, 'a') as f:
                f.write(f"\\n[ACTION]: Calling tool {tool_name} with args {tool_args}")

            if tool_name in tool_map:
                tool_result = tool_map[tool_name](**tool_args)
                with open(scratchpad_path, 'a') as f:
                    f.write(f"\\n[TOOL RESULT]: {tool_result}")

                if tool_name == 'execute_python_code' and "error" in tool_result.lower():
                    agent_status = "Debugging code..."
                    error_prompt = (
                        f"The code execution failed with the following error:\\n{tool_result}\\n\\n"
                        "Please analyze the error and the code that was executed. "
                        "Then, use the file system tools to read the relevant files, "
                        "propose a fix, write the changes to the file, and then try executing the code again."
                    )
                    with open(scratchpad_path, 'a') as f:
                        f.write(f"\\n[DEBUG]: Entering self-correction mode due to error.")
                    chat_session.history.append(genai.protos.Part(text=error_prompt))

            else:
                agent_status = f"Error: Unknown tool {tool_name}"
                with open(scratchpad_path, 'a') as f:
                    f.write(f"\\n[ERROR]: Unknown tool {tool_name}")

    agent_status = "Idle"

def start_agent_loop(goal: str, model_name: str):
    global agent_thread, agent_running
    if agent_running:
        return False
    agent_thread = threading.Thread(target=agent_loop, args=(goal, model_name))
    agent_thread.start()
    return True

def stop_agent_loop():
    global agent_running, agent_thread, agent_status
    if not agent_running:
        return False
    agent_running = False
    if agent_thread:
        agent_thread.join()
        agent_thread = None
    agent_status = "Idle"
    return True

def pause_for_confirmation(prompt: str):
    global agent_status, confirmation_prompt, user_response
    agent_status = "PAUSED_FOR_CONFIRMATION"
    confirmation_prompt = prompt
    confirmation_event.clear()
    confirmation_event.wait() # This will block until the user responds
    return user_response

def respond_to_confirmation(response: str):
    global user_response
    user_response = response
    confirmation_event.set()

def is_agent_running():
    return agent_running

def get_agent_status():
    global agent_status, confirmation_prompt
    if agent_status == "PAUSED_FOR_CONFIRMATION":
        return {"status": agent_status, "prompt": confirmation_prompt}
    return {"status": agent_status}
