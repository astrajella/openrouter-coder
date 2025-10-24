# Autonomous AI Coder Agent

This project is a full-stack, containerized web application that provides a powerful and autonomous AI coder agent. The agent is designed to help with software development tasks by providing a chat interface, a rich set of tools, and an autonomous mode for completing complex goals.

## Features

- **Autonomous Agent Mode**: Assign a high-level goal to the agent, and it will work autonomously to achieve it, using its tools and problem-solving capabilities.
- **Retrieval-Augmented Generation (RAG)**: The agent uses a ChromaDB vector store and sentence transformers to perform semantic searches on the codebase, providing it with relevant context for its tasks.
- **Long-Term Memory**: The agent can summarize its key learnings from a task and save them to a persistent knowledge base, which is then indexed by the RAG system to inform future work.
- **Sandboxed Code Execution**: The agent can execute Python code in a secure, sandboxed Docker container, allowing it to test its own code and verify its solutions.
- **Web Search**: The agent can search the web using the Tavily API to find documentation, research libraries, and look up solutions to errors.
- **Comprehensive File System Tools**: The agent has a full suite of tools for reading, writing, and managing files and directories.
- **Real-Time UI**: The frontend provides a real-time view of the agent's status, scratchpad, and main plan, giving you a clear window into its thought process.
- **Streaming Chat Responses**: The chat interface is highly responsive, with the model's responses streamed to the UI in real time.
- **Dockerized and Production-Ready**: The entire application is containerized using Docker Compose, making it easy to set up, deploy, and scale.

## Architecture

The application is composed of three main services, orchestrated by Docker Compose:

- **`backend`**: A Python Flask application that serves the main API. It handles the agent's core logic, tool execution, and communication with the Google AI models.
- **`frontend`**: A vanilla JavaScript single-page application served by a lightweight Nginx server. It provides the user interface for interacting with the agent.
- **`chroma`**: A ChromaDB instance that serves as the vector store for the RAG system.

## Setup and Installation

To run the application, you will need to have Docker and Docker Compose installed on your system.

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-name>
```

### 2. Create the Environment File

The application requires API keys for Google AI and Tavily. You will need to create a `.env` file in the root of the project with the following content:

```
GOOGLE_API_KEY="your-google-api-key"
TAVILY_API_KEY="your-tavily-api-key"
```

You can use the provided `setup.sh` script to automate this process:

```bash
./setup.sh
```

### 3. Run the Application

Once the `.env` file is in place, you can start the entire application with a single command:

```bash
docker compose up --build
```

This will build the necessary Docker images, start the services, and make the application available at `http://localhost`.

## Usage

- **Chat Mode**: Use the chat interface to interact with the agent, ask questions, and get help with your code.
- **Autonomous Mode**: To start the agent in autonomous mode, enter a high-level goal in the "Autonomous Mode" panel and click "Run Agent". The agent will then begin working on the goal, and you can monitor its progress in the scratchpad and main plan displays.

---
*This project was built with the help of an autonomous AI coder agent.*
