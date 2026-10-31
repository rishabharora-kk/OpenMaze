FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY openmaze ./openmaze
RUN python -m pip install --no-cache-dir .
USER 1000:1000
ENTRYPOINT ["python", "-m", "openmaze"]
