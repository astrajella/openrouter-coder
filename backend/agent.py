# backend/agent.py

import os
import time
import threading
from flask import jsonify
import google.generativeai as genai
from .tools import tool_map, tool_config, read_file, write_file, record_learning, knowledge_base_path

# --- Global State ---
agent_thread = None
stop_event = threading.Event()
agent_state = {
    "status": "stopped",
    "main_plan": "",
    "scratchpad": "",
    "last_tool_output": "",
    "history": [],
    "requires_confirmation": False,
    "confirmation_prompt": "",
}
confirmation_event = threading.Event()
user_confirmation = None

# --- Agent Core ---

def get_base_prompt():
    """Reads the base prompt and knowledge base."""
    base_prompt = read_file("backend/base_prompt.md")
    knowledge_base = read_file(knowledge_base_path)
    return f"{base_prompt}\n\n<knowledge_base>\n{knowledge_base}\n</knowledge_base>"

def get_tdd_prompt():
    """Returns the system prompt with TDD instructions."""
    base_prompt = get_base_prompt()
    tdd_instructions = """
You are now operating in a Test-Driven Development (TDD) workflow. Your primary goal is to ensure all new functionality is verified by tests *before* you write the implementation code.

Your workflow for any new feature or bug fix should be as follows:

1.  **Deconstruct the Task:** Break down the overall goal from the Main Plan into the smallest possible testable unit of functionality. Update your Scratchpad with this specific, small goal.

2.  **RED - Write a Failing Test:**
    *   Before writing any implementation code, write a test that defines and asserts the desired behavior of the new feature.
    *   Use the `write_file` tool to create this test in an appropriate location (e.g., a `tests/` directory).
    *   The test MUST fail when you first run it, because the feature doesn't exist yet.

3.  **Confirm the Test Fails:**
    *   Use the `run_tests` tool to execute the test you just wrote.
    *   Analyze the output to confirm it fails for the expected reason (e.g., 'FunctionNotFound', 'APIError: 404'). If it fails for a different reason (e.g., a syntax error in the test), you must fix the test first.

4.  **GREEN - Write Implementation Code:**
    *   Write the *minimum* amount of code necessary to make the failing test pass.
    *   Use the `write_file` or `rename_file` tools to create or modify the application code.

5.  **Confirm the Test Passes:**
    *   Use the `run_tests` tool again.
    *   If the test passes, you have successfully implemented the feature.
    *   If it still fails, debug your implementation code based on the test output until it passes.

6.  **REFACTOR (Optional but Recommended):**
    *   Once the test is passing, review your implementation code. Can it be made cleaner, more efficient, or more readable without changing its functionality?
    *   If you refactor, run the tests again to ensure you haven't accidentally broken anything.

7.  **Repeat:**
    *   Update your Scratchpad and Main Plan, then move on to the next small, testable unit of functionality.

Always think: "What is the next test I need to write?"
"""
    return f"{base_prompt}\n\n{tdd_instructions}"


def update_agent_state(key, value):
    """Updates the agent's state."""
    agent_state[key] = value

def run_agent_loop(model, goal, auto_approve_flag=False):
    """The main loop for the autonomous agent."""
    global auto_approve
    auto_approve = auto_approve_flag

    update_agent_state("status", "running")

    # Initialize history
    system_prompt = get_tdd_prompt()
    agent_state["history"] = [{"role": "user", "parts": [{"text": f"System Prompt: {system_prompt}\n\nUser Goal: {goal}"}]}]

    while not stop_event.is_set():
        try:
            # Construct the full prompt
            full_prompt = (
                f"Main Plan:\n{agent_state['main_plan']}\n\n"
                f"Scratchpad:\n{agent_state['scratchpad']}\n\n"
                f"Last Tool Output:\n{agent_state['last_tool_output']}\n\n"
                "Based on the plan, your scratchpad, and the last tool output, decide on the next single tool to use. "
                "Think step-by-step in your scratchpad. Then, call the tool."
            )

            # Add the current state to the history for the model
            current_conversation = agent_state["history"] + [{"role": "user", "parts": [{"text": full_prompt}]}]

            response = model.generate_content(
                current_conversation,
                tools=[tool_config],
                generation_config={"temperature": 0.1}
            )

            if not response.candidates or not response.candidates[0].content.parts:
                update_agent_state("last_tool_output", "Error: Model generated an empty response.")
                time.sleep(5)
                continue

            # Extract tool calls
            tool_calls = [part.function_call for part in response.candidates[0].content.parts if part.function_call]

            if not tool_calls:
                # Handle cases where the model generates text instead of a tool call
                text_response = "".join([part.text for part in response.candidates[0].content.parts if part.text])
                update_agent_state("scratchpad", agent_state["scratchpad"] + "\n" + text_response)
                # No tool output to record
                update_agent_state("last_tool_output", "Model generated text instead of a tool call. Continuing.")
                agent_state["history"].append({"role": "model", "parts": [{"text": text_response}]})

            else:
                # Execute tool calls
                api_requests = []
                tool_outputs = []

                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    args = {key: value for key, value in tool_call.args.items()}

                    if tool_name in tool_map:
                        try:
                            # Update scratchpad right before execution
                            thought_process = f"Executing tool: {tool_name} with args: {args}\n"
                            update_agent_state("scratchpad", agent_state["scratchpad"] + "\n" + thought_process)

                            output = tool_map[tool_name](**args)
                            tool_outputs.append({"tool_name": tool_name, "output": output})

                            # Update state immediately after
                            update_agent_state("last_tool_output", output)

                            # Handle confirmation requests
                            if agent_state["requires_confirmation"]:
                                break

                        except Exception as e:
                            error_msg = f"Error executing tool {tool_name}: {e}"
                            tool_outputs.append({"tool_name": tool_name, "output": error_msg})
                            update_agent_state("last_tool_output", error_msg)
                    else:
                        tool_outputs.append({"tool_name": tool_name, "output": f"Tool '{tool_name}' not found."})
                        update_agent_state("last_tool_output", f"Tool '{tool_name}' not found.")

                # Update history with model's turn and tool responses
                agent_state["history"].append({"role": "model", "parts": response.candidates[0].content.parts})

                tool_response_parts = []
                for output in tool_outputs:
                    tool_response_parts.append({
                        "tool_call_id": tool_calls[len(tool_response_parts)].id,
                        "tool_name": output['tool_name'],
                        "content": output['output']
                    })
                agent_state["history"].append({"role": "user", "parts": [{"function_response": {"name": "tool_outputs", "responses": tool_response_parts}}]})

            # Check for confirmation again after processing
            if agent_state["requires_confirmation"]:
                confirmation_event.wait() # Wait for user input
                confirmation_event.clear()

                # Add user's confirmation to history
                agent_state["history"].append({"role": "user", "parts": [{"text": f"User confirmation: {user_confirmation}"}]})

                if user_confirmation == "deny":
                    update_agent_state("last_tool_output", "User denied the action. Please reconsider the plan.")
                else:
                    update_agent_state("last_tool_output", "User approved the action.")

                update_agent_state("requires_confirmation", False)


        except Exception as e:
            error_message = f"An error occurred in the agent loop: {e}"
            update_agent_state("last_tool_output", error_message)
            time.sleep(10) # Wait before retrying

    update_agent_state("status", "stopped")

# --- Control Functions ---

def start_agent_loop(model_name, goal, auto_approve_flag=False):
    """Starts the agent loop in a background thread."""
    global agent_thread, stop_event
    if agent_thread and agent_thread.is_alive():
        return "Agent is already running."

    stop_event.clear()
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(model_name)

    # Reset state for new run
    agent_state.update({
        "main_plan": "The initial goal is to: " + goal,
        "scratchpad": "I need to break down the goal into a series of testable steps.",
        "last_tool_output": "",
        "history": [],
        "requires_confirmation": False,
        "confirmation_prompt": "",
    })

    agent_thread = threading.Thread(target=run_agent_loop, args=(model, goal, auto_approve_flag))
    agent_thread.start()
    return "Agent started successfully."

def stop_agent_loop():
    """Stops the agent loop."""
    global stop_event
    if not agent_thread or not agent_thread.is_alive():
        return "Agent is not running."

    stop_event.set()
    confirmation_event.set() # Release any waiting locks
    agent_thread.join(timeout=5)
    update_agent_state("status", "stopped")
    return "Agent stopped successfully."

def is_agent_running():
    """Checks if the agent thread is alive."""
    return agent_thread and agent_thread.is_alive()

def get_agent_state():
    """Returns the current state of the agent."""
    return agent_state

def pause_for_confirmation(prompt):
    """Pauses the agent and asks for user confirmation."""
    update_agent_state("requires_confirmation", True)
    update_agent_state("confirmation_prompt", prompt)
    confirmation_event.clear()
    return "Waiting for user confirmation..."

def provide_confirmation(confirmation):
    """Provides user confirmation to the agent."""
    global user_confirmation
    if not agent_state["requires_confirmation"]:
        return "No confirmation was requested."

    user_confirmation = confirmation.lower()
    confirmation_event.set()
    return "Confirmation received."

def update_state_manually(new_plan, new_scratchpad):
    """Allows the user to manually update the plan and scratchpad."""
    update_agent_state("main_plan", new_plan)
    update_agent_state("scratchpad", new_scratchpad)
    return "State updated."
