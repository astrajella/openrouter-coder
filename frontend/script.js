document.addEventListener('DOMContentLoaded', () => {
    const modelDropdown = document.getElementById('model-dropdown');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatHistory = document.querySelector('.chat-history');
    const fixErrorButton = document.getElementById('fix-error-button');
    const scratchpad = document.getElementById('scratchpad');
    const mainPlan = document.getElementById('main-plan');

    let conversationHistory = [];

    // Fetch and populate the models
    fetch('http://localhost:5000/models')
        .then(response => response.json())
        .then(models => {
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                modelDropdown.appendChild(option);
            });
        });

    // Fetch and populate the scratchpad and main plan
    fetch('http://localhost:5000/scratchpad')
        .then(response => response.text())
        .then(text => scratchpad.value = text);

    fetch('http://localhost:5000/main_plan')
        .then(response => response.text())
        .then(text => mainPlan.value = text);

    // Send a message
    sendButton.addEventListener('click', () => {
        const message = messageInput.value;
        const selectedModel = modelDropdown.value;

        if (message) {
            sendMessage(message, selectedModel);
        }
    });

    function sendMessage(message, model) {
        appendMessage('user', message);
        conversationHistory.push({role: 'user', parts: [message]});
        messageInput.value = '';

        fetch('http://localhost:5000/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                model: model,
                message: message,
                conversation_history: conversationHistory
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.tool_result) {
                appendMessage('tool', data.tool_result);
                // Send the tool result back to the AI
                sendMessage(data.tool_result, model);
            } else {
                appendMessage('model', data.response);
                conversationHistory.push({role: 'model', parts: [data.response]});
            }
        });
    }

    // Fix an error
    fixErrorButton.addEventListener('click', () => {
        const lastModelResponse = conversationHistory[conversationHistory.length - 1];
        if (lastModelResponse && lastModelResponse.role === 'model') {
            const errorMessage = prompt("Enter the error message:");
            if (errorMessage) {
                fetch('http://localhost:5000/fix_error', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model: modelDropdown.value,
                        error_message: errorMessage,
                        conversation_history: conversationHistory
                    })
                })
                .then(response => response.json())
                .then(data => {
                    appendMessage('model', data.response);
                    conversationHistory.push({role: 'model', parts: [data.response]});
                });
            }
        } else {
            alert("No model response to fix.");
        }
    });

    // Update scratchpad
    scratchpad.addEventListener('blur', () => {
        fetch('http://localhost:5000/scratchpad', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: scratchpad.value
            })
        });
    });

    // Update main plan
    mainPlan.addEventListener('blur', () => {
        fetch('http://localhost:5000/main_plan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: mainPlan.value
            })
        });
    });

    function appendMessage(sender, message) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', `${sender}-message`);
        messageElement.textContent = message;
        chatHistory.appendChild(messageElement);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
});
