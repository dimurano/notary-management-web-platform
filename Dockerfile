# Build stage
FROM python:3.14-slim AS builder

WORKDIR /build
COPY requirements.txt .

# Install dependencies in a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Runtime stage (CHANGED AS builder TO AS runner)
FROM python:3.11-slim AS runner

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# 1. Copy application code AND entrypoint script first
COPY --chown=appuser:appuser . .
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh

# 2. Grant execution permissions while still logged in as ROOT
RUN chmod +x /app/entrypoint.sh

# 3. Create writable directories and set ownership for the whole app folder
RUN mkdir -p /app/data /tmp && \
    chown -R appuser:appuser /app /tmp

# 4. NOW safe to switch to the non-root user
USER appuser

# Expose port
EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]

