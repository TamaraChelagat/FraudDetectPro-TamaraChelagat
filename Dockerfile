# Multi-stage build for FraudDetectPro Backend
FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
# Using production requirements to reduce image size (8GB -> ~1-2GB)
COPY requirements-production.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy startup script
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

# Create directories for models and data
# Files will be provided via Railway Volumes (mount at /app/models and /app/data/processed)
# For local development, you can copy files manually or use volumes
RUN mkdir -p ./models ./data/processed

# Note: Model and data files are NOT copied here
# They should be provided via Railway Volumes or downloaded at runtime
# This allows deployment without committing large files to Git

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run application with uvicorn
# Railway automatically sets PORT environment variable
# Use startup script to handle PORT variable correctly
CMD ["./start.sh"]

