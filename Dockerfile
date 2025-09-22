# syntax=docker/dockerfile:1.8

############################
# Stage 1: Builder
############################
FROM python:3.12-slim AS builder

# Set up environment for faster/cleaner installs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./

RUN python -m venv /venv
ENV PATH="/venv/bin:${PATH}"

# Upgrade pip/setuptools/wheel to improve binary wheel usage
RUN python -m pip install --upgrade pip setuptools wheel

# Install Python deps
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy the rest of your app (delay to maximize cache hits)
COPY src/ .

############################
# Stage 2: Runtime
############################
FROM python:3.12-slim AS runtime

# OCI Labels for container metadata
LABEL org.opencontainers.image.title="Promabbix"
LABEL org.opencontainers.image.description="Tool for connecting Prometheus to Zabbix monitoring"
LABEL org.opencontainers.image.vendor="Wrike"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.url="https://github.com/wrike/promabbix"
LABEL org.opencontainers.image.source="https://github.com/wrike/promabbix"
LABEL org.opencontainers.image.documentation="https://github.com/wrike/promabbix#readme"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Make our venv the default Python
    PATH="/venv/bin:${PATH}"

# Install minimal runtime tools commonly used by Ansible
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      tini \
    && rm -rf /var/lib/apt/lists/*

ARG APP_USER=app
ARG APP_UID=10001
RUN useradd -u "${APP_UID}" -m -s /usr/sbin/nologin "${APP_USER}"

WORKDIR /app

COPY --from=builder /venv /venv
COPY --from=builder /app /app

RUN chown -R ${APP_USER}:${APP_USER} /app /opt/ansible || true
USER ${APP_USER}

# Suggested mount point for input files
VOLUME ["/mnt"]

ENTRYPOINT ["/usr/bin/tini", "--", "python", "promabbix/promabbix.py"]

# Default input, expects to run with a command like
CMD ["-h"]
