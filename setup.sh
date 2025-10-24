#!/bin/bash

# Check for Docker
if ! [ -x "$(command -v docker)" ]; then
  echo "Error: Docker is not installed. Please install Docker before running this script." >&2
  exit 1
fi

# Check for Docker Compose
if ! [ -x "$(command -v docker-compose)" ] && ! [ -x "$(command -v docker compose)" ]; then
  echo "Error: Docker Compose is not installed. Please install Docker Compose before running this script." >&2
  exit 1
fi

# Check if .env file already exists
if [ -f ".env" ]; then
  echo ".env file already exists. Skipping creation."
else
  # Copy .env.template to .env
  cp .env.template .env
  echo "Created .env file. Please edit it to add your API keys."
fi

echo "Setup complete. You can now run the application with 'docker compose up --build'"
