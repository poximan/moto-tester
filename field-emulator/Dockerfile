FROM python:3.12.11-slim-bookworm AS python-deps
WORKDIR /deps
COPY field-emulator/requirements.txt /deps/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /deps/requirements.txt

FROM python:3.12.11-slim-bookworm

ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid "${APP_GID}" appgroup \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /bin/sh appuser \
    && install -d -o "${APP_UID}" -g "${APP_GID}" /emulator /runtime /shared

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/emulator/field-emulator:/shared \
    FIELD_EMULATOR_PORT=8090

WORKDIR /emulator
COPY --chown=${APP_UID}:${APP_GID} moto_time /shared/moto_time
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --chown=${APP_UID}:${APP_GID} field-emulator ./field-emulator

EXPOSE 8090

USER 1000:1000

CMD ["sh", "-c", "exec uvicorn field_emulator.main:app --host 0.0.0.0 --port ${FIELD_EMULATOR_PORT}"]
