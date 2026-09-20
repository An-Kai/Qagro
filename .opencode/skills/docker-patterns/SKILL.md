---
name: docker-patterns
description: Docker best practices, multi-stage builds, container security, Docker Compose orchestration, and deployment patterns. Use when changing the Qagro Dockerfile, docker-compose services, image size, health checks, volumes, or debugging containers.
license: MIT
compatibility: opencode
---

# Docker Patterns Skill

Guidelines for production-ready Docker containers. Source:
https://github.com/Jonathan0823/opencode-config (`skills/docker-patterns`, MIT),
adapted for Qagro.

## Core Principles

### 1. Multi-Stage Builds
- Separate build and runtime environments; minimize final image size.
- Don't include build tools in production.

### 2. Security Hardening
- Run as non-root user where feasible.
- Use specific image tags (not `latest`); scan images for vulnerabilities.

### 3. Layer Caching
- Order instructions by change frequency (deps first, source last).
- Copy package files before source code; use `.dockerignore`.

### 4. Health Checks
- Implement `/health` endpoints; configure Docker health checks with
  appropriate intervals/timeouts/retries.

## Dockerfile Best Practices

```dockerfile
# DO: specific tags
FROM python:3.12-slim
# DO: combine RUN, clean apt lists
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*
# DO: copy deps first for layer caching
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# DO: health check against the app's endpoint
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
```

## Docker Compose Best Practices

```yaml
services:
  app:
    env_file:
      - .env.production
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
```

- Use env files for secrets; set resource limits; configure health checks;
  persist state in named volumes or bind mounts.

## Image Scanning

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest image myapp:latest
docker scout cves myapp:latest
```

## When to Use This Skill

Creating Dockerfiles, setting up dev environments with Compose, optimizing image
sizes, hardening containers, adding health checks, managing dev/staging/prod,
CI/CD with Docker, troubleshooting container issues.

---

## Qagro appendix (project-specific, takes precedence in this repo)

Qagro: `Dockerfile` (`python:3.12-slim`, `fonts-dejavu` for ReportLab Cyrillic,
`pip install -r requirements.txt`, default CMD = API) + `docker-compose.yml`
(services `api` :8000, `bot`, `streamlit` :8501).

Keep these (they are load-bearing, not tech debt):

- Single image, three commands: api `uvicorn src.api:app --host 0.0.0.0 --port 8000`;
  bot `python -m src.bot` (+ `env_file: .env` for `TELEGRAM_BOT_TOKEN`);
  streamlit `streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port 8501`.
- Bind mount `./data:/app/data` on ALL services — persists SQLite `data/cache.db`
  (24 h TTL) across restarts. Never bake `data/cache.db` into the image.
- `EXPOSE 8000 8501`; `restart: unless-stopped`; `bot`/`streamlit` `depends_on: api`.
- `fonts-dejavu` apt package is REQUIRED (PDF Cyrillic); do not remove to "slim"
  the image. `docker compose up --build` is the documented deploy path (README).
- `.env` (token) is git-ignored and mounted only into `bot` — never `COPY .env`
  into the image. Health endpoint for checks: `GET /health` (`{"status":"ok",...}`).
