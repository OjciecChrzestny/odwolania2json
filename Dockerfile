# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72 AS runtime

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

FROM runtime AS adapters
USER 0:0
RUN python -m pip install --no-cache-dir --only-binary=:all: Pillow==13.0.0
COPY experiments/abc/adapters.py experiments/abc/run.py ./experiments/abc/
COPY experiments/transfer_api/crops.py experiments/transfer_api/dates.py \
    experiments/transfer_api/negative_verifier.py experiments/transfer_api/run.py \
    experiments/transfer_api/scaleway.py ./experiments/transfer_api/
USER 1000:1000

FROM runtime AS jury
