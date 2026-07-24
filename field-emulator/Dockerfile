FROM python:3.12-slim

ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid "${APP_GID}" appgroup \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /bin/sh appuser \
    && install -d -o "${APP_UID}" -g "${APP_GID}" /emulator /runtime /shared

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/emulator/field-emulator \
    FIELD_EMULATOR_PORT=8090

WORKDIR /emulator
COPY --chown=${APP_UID}:${APP_GID} field-emulator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=${APP_UID}:${APP_GID} field-emulator ./field-emulator

EXPOSE 8090

USER 1000:1000

CMD ["sh", "-c", "uvicorn field_emulator.main:app --host 0.0.0.0 --port ${FIELD_EMULATOR_PORT}"]
