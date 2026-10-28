FROM node:24-bookworm-slim AS assets
WORKDIR /build
ENV CYPRESS_INSTALL_BINARY=0
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci
COPY frontend/ frontend/
RUN cd frontend && npm run build
COPY vendor/xopat/ vendor/xopat/
COPY scripts/setup_xopat.sh scripts/setup_xopat.sh
RUN bash scripts/setup_xopat.sh \
    && cd vendor/xopat && npm prune --omit=dev --ignore-scripts \
    && rm -rf openseadragon/node_modules openseadragon/.git

FROM python:3.12-slim-bookworm
ARG VERSION=1.0.0
ARG INSTALL_NOTEBOOKS=0
LABEL org.opencontainers.image.title="SPaRE" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.source="https://github.com/human-centered-ai-lab/spare-pathology" \
      org.opencontainers.image.licenses="GPL-3.0-only"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HOME=/tmp
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home spare
COPY --from=assets /usr/local/bin/node /usr/local/bin/node
COPY requirements.txt requirements-notebook.txt ./
RUN pip install --upgrade pip setuptools \
    && pip install -r requirements.txt \
    && if [ "$INSTALL_NOTEBOOKS" = "1" ]; then pip install -r requirements-notebook.txt; fi
COPY app/ app/
COPY config/ config/
COPY scripts/docker_start.sh scripts/docker_start_tiles.sh scripts/
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY --from=assets /build/frontend/dist/ frontend/dist/
COPY --from=assets /build/vendor/xopat/ vendor/xopat/
RUN mkdir -p instance uploads notebooks \
    && chown -R spare:spare instance uploads notebooks
USER spare
EXPOSE 8000
VOLUME ["/app/instance", "/app/uploads", "/app/notebooks"]
CMD ["bash", "/app/scripts/docker_start.sh"]
