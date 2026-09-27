# Scorecard Studio: one image serving the API and the built frontend.
# Build:  docker build -t scorecard-studio .
# Run:    docker compose up   (app + Postgres; migrations run on start)

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npx tsc -b && npx vite build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SCORECARD_AUTO_CREATE=0
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY --from=web /web/dist frontend/dist
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
# migrate, then serve; 2 workers is ample for ~2,400 evaluations/day (measured capacity: ~12 evaluations/s)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers"]
