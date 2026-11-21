# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt requirements-ocr.txt ./
RUN mkdir -m 0755 /opt/tessdata && \
    python -m pip install --no-cache-dir --only-binary=:all: \
        -r requirements.txt -r requirements-ocr.txt

ADD --chmod=0444 --checksum=sha256:c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2 https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/pol.traineddata /opt/tessdata/pol.traineddata
COPY odwolania2json/*.py ./odwolania2json/
COPY odwolania2json/classes/*.json ./odwolania2json/classes/

USER 1000:1000
ENTRYPOINT ["python", "-m", "odwolania2json", "--input", "/work/input", "--output", "/work/output", "--diagnostics", "/work/diagnostics/last-run.json", "--ocr-data", "/opt/tessdata"]
