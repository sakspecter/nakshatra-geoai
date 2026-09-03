# syntax=docker/dockerfile:1
# Project Nakshatra backend — run with:  docker build -t nakshatra-api -f backend/Dockerfile backend
FROM python:3.11-slim AS builder

# System deps for the spatial stack (geopandas/rasterio wheels need libgdal etc.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential curl \
      libgdal-dev gdal-bin \
      libgeos-dev libproj-dev \
      libspatialindex-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Only core runtime deps are copied first for layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Single worker to stay inside Render free plan memory.
# See uvicorn workers note in the deployment guide.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
