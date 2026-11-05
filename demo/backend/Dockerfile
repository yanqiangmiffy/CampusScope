FROM python:3.11-slim

WORKDIR /srv/app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CAMPUSSCOPE_HOME=/srv/campusscope \
    PYTHONPATH=/srv/app:/srv/campusscope

# dependencies first: a code-only change reuses this layer (PIP_INDEX_URL comes from .env via compose)
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt .
RUN pip install -i "$PIP_INDEX_URL" -r requirements.txt

# the system and its data from the repository root (docker-compose.yml: additional_contexts `code` and `data`);
# cache/ (LLM replies and embeddings) is mounted at run time
COPY --from=code . /srv/campusscope/campusscope
COPY --from=data . /srv/campusscope/data
RUN mkdir -p /srv/campusscope/cache /srv/campusscope/outputs

COPY . .

EXPOSE 8000
# slim has no curl: probe with Python
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]
