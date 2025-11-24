# Dockerfile for myst-libre
# Enables myst-libre to run in a Docker container while spawning sibling containers
# on the host machine (Docker-in-Docker scenario)

FROM python:3.11-slim

LABEL maintainer="agahkarakuzu"
LABEL description="MyST-Libre: Reproducible execution environment MyST builds DinD"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    iputils-ping \
    nano \
    netcat-openbsd \
    dnsutils \
    telnet \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Verify Node.js installation
RUN node --version && npm --version

# Install MyST CLI globally
RUN npm install -g mystmd && \
    myst --version

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and git metadata (needed for setuptools_scm)
COPY .git .git
COPY . .

# Install myst-libre in editable mode
# If git metadata is not available, use a fallback version
RUN pip install -e . || \
    SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0 pip install -e .

# Create workspace directories (will be mounted from host)
# These provide structure for the container's perspective
RUN mkdir -p /workspace/builds /workspace/DATA /workspace/config

# Set environment variables for Docker-in-Docker
# These should be overridden when running the container
ENV HOST_WORKSPACE_PATH=""
ENV DOCKER_HOST=""

# Default command
CMD ["python"]
