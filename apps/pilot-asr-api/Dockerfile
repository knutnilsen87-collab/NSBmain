FROM python:3.11-slim

WORKDIR /app

COPY requirements.base.txt .
RUN pip install --no-cache-dir -r requirements.base.txt

COPY app ./app

RUN useradd --create-home --uid 1000 appuser
USER appuser

ENV ASR_BACKEND=mock \
    ASR_MODEL_NAME=mock-small \
    ASR_HOST=0.0.0.0 \
    ASR_PORT=8090

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
