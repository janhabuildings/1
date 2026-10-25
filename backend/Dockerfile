FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 INSPECTION_DATA_DIR=/var/data XDG_DATA_HOME=/var/data XDG_CACHE_HOME=/var/data/.cache
RUN --mount=type=secret,id=build_ca,mode=0444 \
    if [ -s /run/secrets/build_ca ]; then printf 'Acquire::https::CaInfo "/run/secrets/build_ca";\n' > /etc/apt/apt.conf.d/99-build-ca; fi; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get -o APT::Update::Error-Mode=any update && apt-get install -y --no-install-recommends libreoffice-writer fontconfig && rm -rf /var/lib/apt/lists/* && rm -f /etc/apt/apt.conf.d/99-build-ca
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN --mount=type=secret,id=build_ca,mode=0444 \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --no-cache-dir -r backend/requirements.txt
COPY backend /app/backend
COPY backend/fonts /usr/local/share/fonts/jbi
RUN fc-cache -f
COPY report_agent.py requirements.txt /app/
COPY templates /app/templates
COPY plugins /app/plugins
COPY scripts/build_plugin.py /app/scripts/build_plugin.py
RUN python scripts/build_plugin.py && useradd --create-home --uid 10001 inspection && chmod -R a+rX /app && mkdir -p /var/data && chown -R inspection /var/data
USER inspection
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
