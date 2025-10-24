# backend/gemma.py

from google.generativeai.protos import Part, FunctionDeclaration
from .tools import tool_map

def reconstruct_history(conversation_history):
    """Reconstructs the conversation history for the Google AI model."""
    history = []
    for entry in conversation_history:
        role = entry['role']
        parts = []
        for part_data in entry['parts']:
            if 'text' in part_data:
                parts.append(Part(text=part_data['text']))
            elif 'function_call' in part_data:
                fc = part_data['function_call']
                parts.append(Part(function_call=FunctionDeclaration(name=fc['name'], args=fc.get('args', {}))))
            elif 'function_response' in part_data:
                fr = part_data['function_response']
                parts.append(Part(function_response=Part.FunctionResponse(name=fr['name'], response=fr.get('response', {}))))
        history.append({"role": role, "parts": parts})
    return history

def execute_tool_loop(chat_session, history):
    """Executes the tool loop for the Google AI model."""
    last_user_message = history[-1]["parts"]
    response = chat_session.send_message(last_user_message)

    while hasattr(response, 'function_calls') and response.function_calls:
        history.append({"role": "model", "parts": [Part(function_call=fc) for fc in response.function_calls]})

        tool_results = []
        for function_call in response.function_calls:
            tool_name = function_call.name
            tool_args = {key: value for key, value in function_call.args.items()}

            if tool_name in tool_map:
                result = tool_map[tool_name](**tool_args)
            else:
                result = f"Unknown tool: {tool_name}"

            tool_results.append(Part(function_response={"name": tool_name, "response": {"result": result}}))

        history.append({"role": "tool", "parts": tool_results})
        response = chat_session.send_message(tool_results)

    history.append({"role": "model", "parts": [Part(text=response.text)]})
    return response, history

def serializable_history(history):
    """Converts the conversation history to a serializable format."""
    serializable = []
    for h in history:
        parts = []
        for p in h["parts"]:
            if hasattr(p, 'text'):
                parts.append({"text": p.text})
            elif hasattr(p, 'function_call'):
                parts.append({"function_call": {"name": p.function_call.name, "args": dict(p.function_call.args)}})
            elif hasattr(p, 'function_response'):
                parts.append({"function_response": {"name": p.function_response.name, "response": dict(p.function_response.response)}})
        serializable.append({"role": h["role"], "parts": parts})
    return serializable
