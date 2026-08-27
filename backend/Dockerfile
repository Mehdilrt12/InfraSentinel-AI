FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

LABEL org.opencontainers.image.title="InfraSentinel AI backend" \
      org.opencontainers.image.description="Django, Channels and Celery runtime"

RUN groupadd --system --gid 10001 infrasentinel \
    && useradd --system --uid 10001 --gid infrasentinel --home-dir /app infrasentinel

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=infrasentinel:infrasentinel backend/ ./
COPY --chown=infrasentinel:infrasentinel vmware_connector/ ./vmware_connector/
COPY --chown=infrasentinel:infrasentinel hyperv_connector/ ./hyperv_connector/
RUN mkdir -p /app/staticfiles /app/model_store /app/celerybeat \
    && chown -R infrasentinel:infrasentinel /app \
    && chmod 0755 /app/docker-entrypoint.sh

USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["api"]
