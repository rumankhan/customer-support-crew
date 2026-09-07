# Multi-Agent Customer Support Crew — backend (CrewAI + FastAPI)
# Runtime: AAMAD_TARGET_RUNTIME=crewai
# Build from repository root: docker build -t bmobile-support-backend .

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AAMAD_TARGET_RUNTIME=crewai \
    BACKEND_PORT=8001 \
    LOG_DIR=project-context/2.build/logs \
    KB_DIR=backend/kb \
    KB_FILE=articles.csv \
    KB_DB_PATH=backend/data/support.db

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/

RUN mkdir -p /app/project-context/2.build/logs /app/backend/data

EXPOSE 8001

# Bind 0.0.0.0 inside the container only. Publish as 127.0.0.1:8001 on the host
# (see docker-compose.yml) so the LAN is not exposed by default (SEC-04 / SEC-05).
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
