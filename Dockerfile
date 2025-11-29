# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

#add static folder
RUN mkdir /app/static

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    CHROME_BIN=/usr/bin/chromium

# Copy dependency files and source code (required by hatchling)
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy remaining application code
COPY main.py .

# Expose port
EXPOSE $PORT

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
ENTRYPOINT ["sh", "-c"]
CMD ["uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
