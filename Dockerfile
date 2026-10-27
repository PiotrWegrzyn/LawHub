FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# git: the importer writes the law corpus as a git repository.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip
COPY . .
RUN pip install ".[postgres]" \
    && DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

RUN useradd --create-home lawhub && mkdir -p /app/data && chown -R lawhub /app/data
USER lawhub

# Hosting platforms set PORT; migrations are idempotent so running them on boot is safe.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec uvicorn config.asgi:application --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
