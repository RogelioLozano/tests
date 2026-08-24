# Two build stages keep the runtime image lean: the Vue bundle and the Python
# wheels are compiled with toolchains that never reach the final layer.
#
# Manim needs cairo, pango and ffmpeg. It does NOT get LaTeX here — texlive
# would add roughly a gigabyte, so the model is instructed not to emit MathTex.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM python:3.13-slim AS wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libcairo2-dev \
        libpango1.0-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.13-slim AS runtime
# Runtime shared libraries only; the -dev headers stay in the wheels stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=wheels /install /usr/local

WORKDIR /srv
COPY backend/ ./backend/
COPY --from=web /web/dist ./web/dist

# The renderer executes model-generated code. An unprivileged user with no
# write access to the application tree limits what a validator miss can reach.
# UID 1000 specifically: Hugging Face Spaces mounts persistent storage owned by
# that id, and nothing else cares which id it is.
RUN useradd --create-home --uid 1000 render \
    && mkdir -p /data \
    && chown -R render:render /data \
    && chown -R root:root /srv \
    && chmod -R a-w /srv
USER render

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANIM_ENV=production \
    ANIM_LOG_FORMAT=json \
    ANIM_OUTPUT_DIR=/data \
    ANIM_STATIC_DIR=/srv/web/dist \
    ANIM_JOBS_BACKEND=thread \
    ANIM_JOBS_MAX_WORKERS=2

WORKDIR /srv/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

# Single worker: renders are dispatched to the in-process thread pool, so a
# second uvicorn worker would mean two pools competing for the same cores and
# two processes writing the same SQLite file.
CMD ["sh", "-c", "uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
