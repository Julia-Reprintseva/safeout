FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

ENV PYTHONUNBUFFERED=1

# SERVICE_ROLE picks which process to run (bot / worker / api) — lets one
# image serve all three Railway services instead of relying on a
# platform-specific start-command override. Local docker-compose still
# overrides this directly via each service's `command:`.
CMD ["./entrypoint.sh"]
