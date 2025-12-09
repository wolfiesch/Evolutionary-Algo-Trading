FROM python:3.11-slim

WORKDIR /app/crypto

# Install system dependencies including supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY crypto/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (crypto + shared)
COPY crypto/ /app/crypto/
COPY shared/ /app/shared/

# Create logs and shadow pool directories
RUN mkdir -p logs logs/shadow_pool logs/strategies logs/evolution_checkpoints

# Copy supervisor configuration
COPY crypto/supervisor.conf /etc/supervisor/conf.d/crypto-alpha.conf

# Set Python path to include both directories
ENV PYTHONPATH=/app:/app/crypto:$PYTHONPATH

# Default: run with supervisor for process management
# Override with: docker run ... python main.py (for single process mode)
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/crypto-alpha.conf"]
