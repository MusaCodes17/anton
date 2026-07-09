# Anton backend — Python 3.11 + Playwright/Chromium + Litestream
#
# INV-9: exactly one Uvicorn worker is required (D4 scrape lock + E8 rate
# limiter are in-process; multiple workers give each its own lock state and
# rate-limit bucket, silently breaking both invariants). See CLAUDE.md §14.
#
# RA1.4: Litestream is installed in the image. entrypoint.sh enables it only
# when LITESTREAM_BUCKET is set at runtime — safe to run without it in dev.
FROM python:3.11-slim

# Playwright needs wget + ca-certificates before it can self-install OS deps.
# sqlite3 CLI is used by pull-snapshot.sh to verify restored DB counts.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Litestream for continuous SQLite replication (RA1.4).
# dpkg --print-architecture returns "amd64" or "arm64" — matches the Litestream
# GitHub release filenames exactly. Pinned version; bump intentionally.
ARG LITESTREAM_VERSION=v0.3.13
RUN ARCH="$(dpkg --print-architecture)" \
    && wget -qO /tmp/litestream.tar.gz \
       "https://github.com/benbjohnson/litestream/releases/download/${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-${ARCH}.tar.gz" \
    && tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin litestream \
    && rm /tmp/litestream.tar.gz \
    && litestream version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium and all its OS-level shared libraries.
# Only Chromium is needed — used by the bespoke Asics scraper and Algolia
# headless flows. `--with-deps` handles the full apt dependency chain.
RUN playwright install --with-deps chromium

# Copy the backend source (alembic/, app/, alembic.ini, run.py, litestream.yml, …)
COPY . .

# Make entrypoint executable after COPY (it's in the repo as plain text).
RUN chmod +x /app/entrypoint.sh

# Timezone: run_date logic passes America/Toronto explicitly throughout, but
# setting TZ at the OS level ensures nothing can silently read the host clock
# in UTC. RA1.2 risk table: "Host clock/timezone drift: run_date off-by-one."
ENV TZ=America/Toronto

EXPOSE 8000

# entrypoint.sh handles Litestream restore-on-start + replication when
# LITESTREAM_BUCKET is set, then execs uvicorn (one worker — INV-9).
# Without LITESTREAM_BUCKET it runs uvicorn directly (dev mode).
CMD ["/app/entrypoint.sh"]
