# Use the official slim Python base image
FROM python:3.12-slim

# Set environment variables to optimize Python execution
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies if required (Optional: omit if your app only needs pip packages)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python packages
RUN pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create and switch to a non-privileged user for security compliance
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Expose the application port (change to match your app)
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]
