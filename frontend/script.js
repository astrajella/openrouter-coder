document.addEventListener('DOMContentLoaded', () => {
    const modelDropdown = document.getElementById('model-dropdown');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatHistory = document.querySelector('.chat-history');
    const loadingIndicator = document.querySelector('.loading-indicator-container');
    const fixErrorButton = document.getElementById('fix-error-button');
    const indexButton = document.getElementById('index-button');
    const indexingStatus = document.getElementById('indexing-status');
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

    async function sendMessage(message, model) {
        appendMessage('user', message);
        conversationHistory.push({role: 'user', parts: [{"text": message}]});
        messageInput.value = '';
        loadingIndicator.style.display = 'flex';

        fetch('http://localhost:5000/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: model,
                message: message,
                conversation_history: conversationHistory.slice(0, -1) // Send history without the current message
            })
        })
        .then(response => response.json())
        .then(data => {
            loadingIndicator.style.display = 'none';
            conversationHistory = data.history;
            renderHistory();
        });
    }

    function renderHistory() {
        chatHistory.innerHTML = '';
        conversationHistory.forEach(turn => {
            if (turn.role === 'user') {
                appendMessage('user', turn.parts[0].text);
            } else if (turn.role === 'model') {
                if (turn.parts[0].function_call) {
                    const fc = turn.parts[0].function_call;
                    appendMessage('tool', `Tool Call: ${fc.name}(${JSON.stringify(fc.args)})`);
                } else {
                    appendMessage('model', turn.parts[0].text);
                }
            } else if (turn.role === 'tool') {
                const fr = turn.parts[0].function_response;
                appendMessage('tool', `Tool Result: ${fr.response.result}`);
            }
        });
    }

    // Fix an error
    fixErrorButton.addEventListener('click', async () => {
        const lastModelResponse = conversationHistory[conversationHistory.length - 1];
        if (lastModelResponse && lastModelResponse.role === 'model') {
            const errorMessage = prompt("Enter the error message:");
            if (errorMessage) {
                loadingIndicator.style.display = 'flex';
                fetch('http://localhost:5000/fix_error', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        model: modelDropdown.value,
                        error_message: errorMessage,
                        conversation_history: conversationHistory
                    })
                })
                .then(response => response.json())
                .then(data => {
                    loadingIndicator.style.display = 'none';
                    conversationHistory = data.history;
                    renderHistory();
                });
            }
        } else {
            alert("No model response to fix.");
        }
    });

    // Index the codebase
    indexButton.addEventListener('click', () => {
        indexingStatus.textContent = 'Indexing...';
        fetch('http://localhost:5000/index', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                indexingStatus.textContent = 'Indexing complete!';
            } else {
                indexingStatus.textContent = 'Indexing failed.';
            }
        });
    });

    // Update scratchpad and main plan
    scratchpad.addEventListener('blur', () => updateState('scratchpad', scratchpad.value));
    mainPlan.addEventListener('blur', () => updateState('main_plan', mainPlan.value));

    function updateState(endpoint, content) {
        fetch(`http://localhost:5000/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content })
        });
    }

    function appendMessage(sender, message) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', `${sender}-message`);
        messageElement.textContent = message;
        chatHistory.appendChild(messageElement);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return messageElement;
    }
});
