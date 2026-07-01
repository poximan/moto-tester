FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/emulator/field-emulator

WORKDIR /emulator
COPY field-emulator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY field-emulator ./field-emulator

CMD ["sh", "-c", "uvicorn field_emulator.main:app --host 0.0.0.0 --port ${FIELD_EMULATOR_PORT}"]
