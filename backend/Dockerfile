# Anton backend — Python 3.11 + Playwright/Chromium
#
# INV-9: exactly one Uvicorn worker is required (D4 scrape lock + E8 rate
# limiter are in-process; multiple workers give each its own lock state and
# rate-limit bucket, silently breaking both invariants). See CLAUDE.md §14.
FROM python:3.11-slim

# Playwright needs wget + ca-certificates before it can self-install OS deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium and all its OS-level shared libraries.
# Only Chromium is needed — used by the bespoke Asics scraper and Algolia
# headless flows. `--with-deps` handles the full apt dependency chain.
RUN playwright install --with-deps chromium

# Copy the backend source (alembic/, app/, alembic.ini, run.py, …)
COPY . .

# Timezone: run_date logic passes America/Toronto explicitly throughout, but
# setting TZ at the OS level ensures nothing can silently read the host clock
# in UTC. RA1.2 risk table: "Host clock/timezone drift: run_date off-by-one."
ENV TZ=America/Toronto

EXPOSE 8000

# One worker — not a default, an invariant (INV-9).
# To increase workers, first redesign D4's scrape lock and E8's rate limiter
# to be multi-process-safe (see docs/design_decisions.md D4/E8).
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
