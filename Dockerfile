FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ICPQ_DATA=/data ICPQ_HOST=0.0.0.0 ICPQ_PORT=8890
RUN useradd -r -u 10001 -m icpq && mkdir /data && chown icpq /data
WORKDIR /app
COPY icpq ./icpq
COPY samples ./samples
USER icpq
EXPOSE 8890
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8890/healthz',timeout=4)"
CMD ["python", "-m", "icpq", "serve"]
