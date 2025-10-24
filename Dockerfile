FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the script to the container
COPY temp_code.py .

# Run the script
CMD ["python", "temp_code.py"]
