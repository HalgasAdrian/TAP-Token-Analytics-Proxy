# syntax=docker/dockerfile:1

# Dashboard build. No API URL is passed in: the bundle uses relative paths and
# is served by the API itself, same origin.
FROM node:20-alpine AS dashboard
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Shared dependency layer.
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Test and lint image: dev tooling, the suite, and the local dev utilities.
FROM base AS dev
COPY backend/requirements-dev.txt ./requirements-dev.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY backend/dev ./dev
COPY backend/tests ./tests
CMD ["pytest"]

# Production image, last so a bare `docker build` produces it. Application code
# only, no dev dependencies, running unprivileged.
FROM base AS runtime
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY --from=dashboard /build/dist ./static
RUN useradd --create-home --uid 10001 tap && chown -R tap:tap /app
USER tap
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
