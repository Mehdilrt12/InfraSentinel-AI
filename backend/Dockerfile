FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY vmware_connector/ ./vmware_connector/
COPY hyperv_connector/ ./hyperv_connector/
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
