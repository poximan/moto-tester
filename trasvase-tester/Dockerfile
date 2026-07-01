FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/trasvase-tester

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY trasvase-tester ./trasvase-tester
COPY config ./config
COPY docs ./docs

CMD ["sh", "-c", "uvicorn app.main:app --host ${WEB_HOST} --port ${WEB_PORT}"]
