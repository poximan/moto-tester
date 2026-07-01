FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /emulator
COPY field_emulator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY field_emulator ./field_emulator

CMD ["sh", "-c", "uvicorn field_emulator.main:app --host 0.0.0.0 --port ${FIELD_EMULATOR_PORT}"]
