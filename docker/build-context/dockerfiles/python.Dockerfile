FROM python:3.12-slim

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl default-jre-headless procps \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-python.txt /tmp/requirements-python.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements-python.txt \
    && rm /tmp/requirements-python.txt

WORKDIR /workspace
