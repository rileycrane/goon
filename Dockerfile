FROM python:3.12-slim

WORKDIR /app

# Install Litestream for SQLite replication
ADD https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz /tmp/litestream.tar.gz
RUN tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin && rm /tmp/litestream.tar.gz

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ app/
COPY scripts/ scripts/
COPY litestream.yml /etc/litestream.yml

RUN mkdir -p /data/users

CMD litestream replicate -exec "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}" -config /etc/litestream.yml
