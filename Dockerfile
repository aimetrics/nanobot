FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates git bubblewrap openssh-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p nanobot && touch nanobot/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf nanobot

# Copy the full source and install
COPY nanobot/ nanobot/
RUN uv pip install --system --no-cache .

# Create non-root user and config directory
RUN useradd -m -u 1000 -s /bin/bash nanobot && \
    mkdir -p /home/nanobot/.nanobot && \
    chown -R nanobot:nanobot /home/nanobot /app

USER nanobot
ENV HOME=/home/nanobot

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["nanobot"]
CMD ["status"]
