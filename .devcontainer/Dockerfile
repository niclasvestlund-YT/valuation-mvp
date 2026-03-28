FROM mcr.microsoft.com/devcontainers/python:1-3.11-bullseye

# Native deps for pillow-heif (HEIC/HEIF image support) and pillow-avif
RUN apt-get update && apt-get install -y --no-install-recommends \
    libheif-dev \
    libde265-dev \
    libffi-dev \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# Pre-install Python deps (cached layer — rebuild only when requirements.txt changes)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
