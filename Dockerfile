FROM python:3.11-slim

# Install system dependencies including ffmpeg and nodejs (for JS challenge solving)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment config
ENV PORT=10000
ENV PYTHONUNBUFFERED=1

EXPOSE 10000

CMD ["sh", "-c", "gunicorn app:app --workers 2 --threads 4 --timeout 180 --bind 0.0.0.0:${PORT:-10000}"]
