FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including psql)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Rust-based ultra-fast Python package installer)
RUN pip install --no-cache-dir uv

COPY requirements.txt ./
RUN uv pip install --system --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY alembic.ini ./
# COPY app/migrations ./migrations

#EXPOSE 4000

# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4000", "--loop", "uvloop"]