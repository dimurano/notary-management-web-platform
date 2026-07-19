#!/bin/bash
# Entrypoint script for Cloud Run
set -e

echo "Starting Notary API..."
echo "Environment: ${ENVIRONMENT:-production}"
echo "Port: ${PORT:-8080}"

# Run the FastAPI application
exec uvicorn main:app \
  --host 0.0.0.0 \
  --port ${PORT:-8080} \
  --workers 1 \
  --timeout-keep-alive 65 \
  --timeout-graceful-shutdown 30
