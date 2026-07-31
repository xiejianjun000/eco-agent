# syntax=docker/dockerfile:1
# ECO AGENT all-in-one image
# - Multi-stage: deps are installed into a venv during build, runtime copies only the venv.
# - Runtime runs as non-root user `eco`.
# - bubblewrap (bwrap) + slirp4netns provide the offline network-sandbox for tool execution.

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt


FROM python:3.12-slim AS runtime

# bubblewrap: sandbox for untrusted command execution; slirp4netns: unprivileged netns
RUN apt-get update && \
    apt-get install -y --no-install-recommends bubblewrap slirp4netns ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# non-root runtime user
RUN groupadd --system eco && useradd --system --gid eco --create-home eco

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . /app
RUN chown -R eco:eco /app

USER eco

EXPOSE 8000 7070

ENTRYPOINT ["python", "-m", "eco.cli"]
CMD ["--help"]
