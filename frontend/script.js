document.addEventListener('DOMContentLoaded', () => {
    const modelDropdown = document.getElementById('model-dropdown');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatHistory = document.querySelector('.chat-history');
    const loadingIndicator = document.querySelector('.loading-indicator-container');
    const fixErrorButton = document.getElementById('fix-error-button');
    const indexButton = document.getElementById('index-button');
    const indexingStatus = document.getElementById('indexing-status');
    const goalInput = document.getElementById('goal-input');
    const runAgentButton = document.getElementById('run-agent-button');
    const stopAgentButton = document.getElementById('stop-agent-button');
    const agentStatusSpan = document.getElementById('agent-status');

    const scratchpadTextarea = document.getElementById('scratchpad');
    const mainPlanTextarea = document.getElementById('main-plan');
    const scratchpadMd = document.getElementById('scratchpad-md');
    const mainPlanMd = document.getElementById('main-plan-md');

    let conversationHistory = [];
    let statusInterval;
    const API_BASE_URL = '/';

    fetch(`${API_BASE_URL}models`)
        .then(response => response.json())
        .then(models => {
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                modelDropdown.appendChild(option);
            });
        });

    fetch(`${API_BASE_URL}scratchpad`).then(response => response.text()).then(text => {
        scratchpadTextarea.value = text;
        scratchpadMd.innerHTML = marked.parse(text);
    });
    fetch(`${API_BASE_URL}main_plan`).then(response => response.text()).then(text => {
        mainPlanTextarea.value = text;
        mainPlanMd.innerHTML = marked.parse(text);
    });

    sendButton.addEventListener('click', () => {
        const message = messageInput.value;
        const selectedModel = modelDropdown.value;
        if (message) sendMessage(message, selectedModel);
    });

    messageInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendButton.click();
        }
    });

    async function sendMessage(message, model) {
        appendMessage('user', message);
        conversationHistory.push({role: 'user', parts: [{"text": message}]});
        messageInput.value = '';
        loadingIndicator.style.display = 'flex';

        const modelMessageElement = appendMessage('model', '');
        let fullResponse = '';

        try {
            const response = await fetch(`${API_BASE_URL}chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: model,
                    message: message,
                    conversation_history: conversationHistory.slice(0, -1)
                })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const rawSse = decoder.decode(value);
                const sseMessages = rawSse.split('\\n\\n').filter(Boolean);

                for (const sseMessage of sseMessages) {
                    if (sseMessage.startsWith('data:')) {
                        try {
                            const dataStr = sseMessage.substring(5).trim();
                            const data = JSON.parse(dataStr);
                            if (data.chunk) {
                                fullResponse += data.chunk;
                                modelMessageElement.innerHTML = marked.parse(fullResponse);
                                chatHistory.scrollTop = chatHistory.scrollHeight;
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data:', e);
                        }
                    }
                }
            }
        } catch (error) {
            modelMessageElement.innerHTML = "Error fetching response.";
            console.error('Fetch error:', error);
        } finally {
            loadingIndicator.style.display = 'none';
            conversationHistory.push({ role: 'model', parts: [{ "text": fullResponse }] });
        }
    }

    function renderHistory() {
        const modelMessages = chatHistory.querySelectorAll('.model-message');
        if(modelMessages.length > 0) {
            const lastModelMessage = modelMessages[modelMessages.length - 1];
            const lastResponse = conversationHistory[conversationHistory.length - 1];
            if(lastResponse && lastResponse.role === 'model'){
                 lastModelMessage.innerHTML = marked.parse(lastResponse.parts[0].text);
            }
        }
    }


    runAgentButton.addEventListener('click', () => {
        const goal = goalInput.value;
        const model = modelDropdown.value;
        if (!goal) {
            alert("Please enter a goal for the agent.");
            return;
        }
        fetch(`${API_BASE_URL}execute_plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal: goal, model: model })
        }).then(() => {
            runAgentButton.disabled = true;
            stopAgentButton.disabled = false;
            agentStatusSpan.textContent = "Running...";
            statusInterval = setInterval(pollStatus, 2000);
        });
    });

    stopAgentButton.addEventListener('click', () => {
        fetch(`${API_BASE_URL}stop_agent`, { method: 'POST' }).then(() => {
            runAgentButton.disabled = false;
            stopAgentButton.disabled = true;
            agentStatusSpan.textContent = "Idle";
            clearInterval(statusInterval);
        });
    });

    function pollStatus() {
        fetch(`${API_BASE_URL}status`)
            .then(response => response.json())
            .then(data => {
                scratchpadTextarea.value = data.scratchpad;
                mainPlanTextarea.value = data.main_plan;
                scratchpadMd.innerHTML = marked.parse(data.scratchpad);
                mainPlanMd.innerHTML = marked.parse(data.main_plan);
                agentStatusSpan.textContent = data.agent_status;

                if (!data.agent_running) {
                    runAgentButton.disabled = false;
                    stopAgentButton.disabled = true;
                    agentStatusSpan.textContent = "Idle";
                    clearInterval(statusInterval);
                    alert("Agent has finished its task.");
                }
            });
    }

    fixErrorButton.addEventListener('click', async () => {
        const lastModelResponse = conversationHistory[conversationHistory.length - 1];
        if (lastModelResponse && lastModelResponse.role === 'model') {
            const errorMessage = prompt("Enter the error message:");
            if (errorMessage) {
                loadingIndicator.style.display = 'flex';
                const modelMessageElement = appendMessage('model', '');
                let fullResponse = '';

                try {
                    const response = await fetch(`${API_BASE_URL}fix_error`, {
                         method: 'POST',
                         headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({
                             model: modelDropdown.value,
                             error_message: errorMessage,
                             conversation_history: conversationHistory
                         })
                     });

                     const reader = response.body.getReader();
                     const decoder = new TextDecoder();

                     while (true) {
                         const { value, done } = await reader.read();
                         if (done) break;

                         const rawSse = decoder.decode(value);
                         const sseMessages = rawSse.split('\\n\\n').filter(Boolean);

                         for (const sseMessage of sseMessages) {
                             if (sseMessage.startsWith('data:')) {
                                 const dataStr = sseMessage.substring(5);
                                 const data = JSON.parse(dataStr);
                                 if (data.chunk) {
                                     fullResponse += data.chunk;
                                     modelMessageElement.innerHTML = marked.parse(fullResponse);
                                     chatHistory.scrollTop = chatHistory.scrollHeight;
                                 }
                             }
                         }
                     }
                } catch (e) {
                    modelMessageElement.innerHTML = "Error fetching response.";
                } finally {
                    loadingIndicator.style.display = 'none';
                    conversationHistory.push({ role: 'model', parts: [{ "text": fullResponse }] });
                }
            }
        } else {
            alert("No model response to fix.");
        }
    });


    indexButton.addEventListener('click', () => {
        indexingStatus.textContent = 'Indexing...';
        fetch(`${API_BASE_URL}index`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                indexingStatus.textContent = 'Indexing complete!';
            } else {
                indexingStatus.textContent = 'Indexing failed.';
            }
        });
    });

    scratchpadTextarea.addEventListener('input', () => {
        const content = scratchpadTextarea.value;
        scratchpadMd.innerHTML = marked.parse(content);
        updateState('scratchpad', content);
    });

    mainPlanTextarea.addEventListener('input', () => {
        const content = mainPlanTextarea.value;
        mainPlanMd.innerHTML = marked.parse(content);
        updateState('main_plan', content);
    });

    function updateState(endpoint, content) {
        fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content })
        });
    }

    function appendMessage(sender, message) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', `${sender}-message`, 'markdown-body');
        messageElement.innerHTML = marked.parse(message);
        chatHistory.appendChild(messageElement);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return messageElement;
    }

    function appendStructuredMessage(type, html) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', `${type}-message`);
        messageElement.innerHTML = html;
        chatHistory.appendChild(messageElement);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return messageElement;
    }
});
