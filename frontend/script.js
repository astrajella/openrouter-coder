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
    const goalInput = document.getElementById('goal-input');
    const runAgentButton = document.getElementById('run-agent-button');
    const stopAgentButton = document.getElementById('stop-agent-button');

    let conversationHistory = [];
    let statusInterval;

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
    fetch('http://localhost:5000/scratchpad').then(response => response.text()).then(text => scratchpad.value = text);
    fetch('http://localhost:5000/main_plan').then(response => response.text()).then(text => mainPlan.value = text);

    // Send a message
    sendButton.addEventListener('click', () => {
        const message = messageInput.value;
        const selectedModel = modelDropdown.value;
        if (message) sendMessage(message, selectedModel);
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
                conversation_history: conversationHistory.slice(0, -1)
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
            const part = turn.parts[0];
            if (turn.role === 'user') {
                appendMessage('user', part.text);
            } else if (turn.role === 'model') {
                if (part.function_call) {
                    appendMessage('tool', `Tool Call: ${part.function_call.name}(${JSON.stringify(part.function_call.args)})`);
                } else {
                    appendMessage('model', part.text);
                }
            } else if (turn.role === 'tool') {
                appendMessage('tool', `Tool Result: ${part.function_response.response.result}`);
            }
        });
    }

    // Agent Controls
    runAgentButton.addEventListener('click', () => {
        const goal = goalInput.value;
        const model = modelDropdown.value;
        if (!goal) {
            alert("Please enter a goal for the agent.");
            return;
        }
        fetch('http://localhost:5000/execute_plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal: goal, model: model })
        }).then(() => {
            runAgentButton.disabled = true;
            stopAgentButton.disabled = false;
            statusInterval = setInterval(pollStatus, 2000);
        });
    });

    stopAgentButton.addEventListener('click', () => {
        fetch('http://localhost:5000/stop_agent', { method: 'POST' }).then(() => {
            runAgentButton.disabled = false;
            stopAgentButton.disabled = true;
            clearInterval(statusInterval);
        });
    });

    function pollStatus() {
        fetch('http://localhost:5000/status')
            .then(response => response.json())
            .then(data => {
                scratchpad.value = data.scratchpad;
                mainPlan.value = data.main_plan;
                if (!data.agent_running) {
                    runAgentButton.disabled = false;
                    stopAgentButton.disabled = true;
                    clearInterval(statusInterval);
                    alert("Agent has finished its task.");
                }
            });
    }

    // Other sidebar functions
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
