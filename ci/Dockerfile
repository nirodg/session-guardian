# Test image for SessionGuardian's local CI: official Python + Git, nothing else.
ARG PY=3.12
FROM python:${PY}-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system user.email "ci@example.invalid" \
 && git config --system user.name "Local CI" \
 && git config --system safe.directory '*' \
 && git config --system init.defaultBranch main \
 && useradd --create-home ci
USER ci
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /home/ci
