"""
FastMCP instance, transport-security config and DB-session helper for the MCP server.

Mounted onto the FastAPI app (see app/main.py) at /mcp via
mcp.streamable_http_app(), using Streamable HTTP transport.

Domain modules import `mcp` from here and open sessions via
`_core.get_session()` (always through the module attribute, so a single
monkeypatch of `app.mcp_server._core.get_session` reaches every tool).
"""
import os

from contextlib import contextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.database import SessionLocal

# DNS-rebinding protection (mcp SDK): the Streamable HTTP transport validates
# the request Host against an allowlist defaulting to localhost only. Behind
# Caddy the Host is the public domain, so it must be added explicitly or every
# proxied request is rejected with 421 *before* reaching the app (hence no
# access-log line). Localhost entries kept for dev/tests/health probe.
_allowed_hosts = [h.strip() for h in os.getenv(
    "ANTON_ALLOWED_HOSTS", "localhost,localhost:8000,127.0.0.1,127.0.0.1:8000"
).split(",") if h.strip()]
_allowed_origins = [o.strip() for o in os.getenv("ANTON_ALLOWED_ORIGINS", "").split(",") if o.strip()] \
    or [f"https://{h}" for h in _allowed_hosts if ":" not in h]

# streamable_http_path="/" because the app this is mounted under (main.py)
# already adds the "/mcp" prefix — else the route is at the doubled "/mcp/mcp".
mcp = FastMCP(
    "anton",
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=_allowed_hosts,
        allowed_origins=_allowed_origins,
    ),
)


@contextmanager
def get_session():
    """Same open/close lifecycle as app.database.get_db, for use outside FastAPI's DI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
