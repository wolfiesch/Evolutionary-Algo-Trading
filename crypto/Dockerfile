FROM python:3.11-slim

WORKDIR /app/crypto

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY crypto/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (crypto + shared)
COPY crypto/ /app/crypto/
COPY shared/ /app/shared/

# Create logs directory
RUN mkdir -p logs

# Set Python path to include both directories
ENV PYTHONPATH=/app:/app/crypto:$PYTHONPATH

# Run the main application
CMD ["python", "main.py"]
