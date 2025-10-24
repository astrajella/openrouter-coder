# backend/agent.py

import threading
import google.generativeai as genai
from .tools import tool_config, tool_map
from .app import main_plan_path, scratchpad_path

agent_thread = None
agent_running = False

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

        if not hasattr(response, 'function_calls') or not response.function_calls:
            with open(scratchpad_path, 'a') as f:
                f.write(f"\\n[AGENT]: {response.text}")
            continue

        for function_call in response.function_calls:
            tool_name = function_call.name
            tool_args = {key: value for key, value in function_call.args.items()}

            with open(scratchpad_path, 'a') as f:
                f.write(f"\\n[ACTION]: Calling tool {tool_name} with args {tool_args}")

            if tool_name in tool_map:
                tool_result = tool_map[tool_name](**tool_args)
                with open(scratchpad_path, 'a') as f:
                    f.write(f"\\n[TOOL RESULT]: {tool_result}")
            else:
                with open(scratchpad_path, 'a') as f:
                    f.write(f"\\n[ERROR]: Unknown tool {tool_name}")

def start_agent_loop(goal: str, model_name: str):
    global agent_thread, agent_running
    if agent_running:
        return False
    agent_thread = threading.Thread(target=agent_loop, args=(goal, model_name))
    agent_thread.start()
    return True

def stop_agent_loop():
    global agent_running, agent_thread
    if not agent_running:
        return False
    agent_running = False
    if agent_thread:
        agent_thread.join()
        agent_thread = None
    return True

def is_agent_running():
    return agent_running
