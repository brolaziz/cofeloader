FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    DOWNLOAD_DIR=/tmp/cofesave

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY requirements.lock ./
RUN pip install -r requirements.lock
COPY bot.py ./
COPY cofesave ./cofesave
COPY assets/brand ./assets/brand

CMD ["python", "bot.py"]
