FROM python:3.12-slim

WORKDIR /w

RUN apt-get update && apt-get install -y --no-install-recommends \
  ffmpeg \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir redis httpx boto3

COPY src /w/src

CMD ["python", "-u", "/w/src/worker.py"]

