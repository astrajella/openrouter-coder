# backend/gemma.py

from google.generativeai.protos import Part, FunctionDeclaration
from .tools import tool_map
import json

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

def handle_tool_calls(chat_session, history):
    """
    Handles the non-streaming part of the conversation: executing tool calls.
    Returns the updated history. The chat_session is stateful and is also updated.
    """
    last_user_message = history[-1]["parts"]
    # Send the user's message to the model.
    response = chat_session.send_message(last_user_message)

    # Loop as long as the model is requesting tool calls.
    while hasattr(response, 'function_calls') and response.function_calls:
        # Add the model's tool call request to the history.
        history.append({"role": "model", "parts": [Part(function_call=fc) for fc in response.function_calls]})

        tool_results = []
        # Execute each tool call and collect the results.
        for function_call in response.function_calls:
            tool_name = function_call.name
            tool_args = {key: value for key, value in function_call.args.items()}

            if tool_name in tool_map:
                result = tool_map[tool_name](**tool_args)
            else:
                result = f"Unknown tool: {tool_name}"

            tool_results.append(Part(function_response={"name": tool_name, "response": {"result": result}}))

        # Add the tool execution results to the history.
        history.append({"role": "tool", "parts": tool_results})

        # Send the tool results back to the model to continue the conversation.
        response = chat_session.send_message(tool_results)

    # Once the loop finishes, the `response` contains the complete, non-streamed final text.
    # We add this to the history so the streaming function knows the full history.
    history.append({"role": "model", "parts": [Part(text=response.text)]})
    return history

def stream_chat_response(chat_session, history):
    """
    Takes a chat session with full history and streams the final response.
    This function assumes the last message in the history is the one to respond to.
    """
    # Get a streaming response from the model.
    response_stream = chat_session.send_message(history[-1]["parts"], stream=True)

    # Yield each chunk of text as it arrives.
    for chunk in response_stream:
        if chunk.text:
            # Format as a Server-Sent Event (SSE).
            yield f"data: {json.dumps({'chunk': chunk.text})}\\n\\n"

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
