"""
OAuth 2.1 login page (RA1.1b).

Owns the one human-facing step in the OAuth flow: the password gate that
the Authorization Server redirects to after /authorize validates the client
and PKCE params.

GET  /oauth/login  — render the password form with all OAuth params as hidden fields
POST /oauth/login  — validate the password; on success, create an auth code and
                     redirect to redirect_uri?code=...&state=...; on failure,
                     re-render the form with an error (no rate-limit here — RA1.3
                     handles brute-force via the upstream rate limiter).

All OAuth params are passed stateless through the form's hidden inputs (not
session state). The code_challenge is not secret; secrecy lives in the client's
code_verifier. The TLS layer (Caddy) prevents eavesdropping.

The ANTON_LOGIN_PASSWORD is compared via secrets.compare_digest (timing-safe).
"""
from __future__ import annotations

import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.oauth import create_auth_code

router = APIRouter(tags=["oauth"])

# Minimal login page HTML template.  Inline styles only — no external assets,
# no JS required.  Must render correctly on mobile (the user is likely on iOS).
_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Anton — Sign in</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0f172a;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      min-height: 100dvh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 2.5rem 2rem;
      width: 100%;
      max-width: 360px;
    }}
    h1 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 0.25rem; }}
    .subtitle {{ color: #94a3b8; font-size: 0.85rem; margin-bottom: 2rem; }}
    label {{ display: block; font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.375rem; }}
    input[type=password] {{
      width: 100%;
      padding: 0.625rem 0.75rem;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      color: #e2e8f0;
      font-size: 1rem;
      outline: none;
      margin-bottom: 1.25rem;
    }}
    input[type=password]:focus {{ border-color: #3b82f6; }}
    .error {{
      background: #450a0a;
      border: 1px solid #b91c1c;
      border-radius: 6px;
      color: #fca5a5;
      font-size: 0.85rem;
      padding: 0.5rem 0.75rem;
      margin-bottom: 1.25rem;
    }}
    button {{
      width: 100%;
      padding: 0.625rem;
      background: #3b82f6;
      border: none;
      border-radius: 6px;
      color: #fff;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
    }}
    button:hover {{ background: #2563eb; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Anton</h1>
    <p class="subtitle">MCP connector authorization</p>
    {error_block}
    <form method="post" action="/oauth/login">
      <input type="hidden" name="code_challenge" value="{code_challenge}">
      <input type="hidden" name="redirect_uri" value="{redirect_uri}">
      <input type="hidden" name="redirect_uri_provided_explicitly" value="{redirect_uri_provided_explicitly}">
      <input type="hidden" name="client_id" value="{client_id}">
      <input type="hidden" name="state" value="{state}">
      <input type="hidden" name="scope" value="{scope}">
      <input type="hidden" name="resource" value="{resource}">
      <label for="pw">Password</label>
      <input type="password" id="pw" name="password" autofocus autocomplete="current-password">
      <button type="submit">Sign in</button>
    </form>
  </div>
</body>
</html>"""


def _render_login(
    *,
    code_challenge: str = "",
    redirect_uri: str = "",
    redirect_uri_provided_explicitly: str = "1",
    client_id: str = "",
    state: str = "",
    scope: str = "",
    resource: str = "",
    error: str = "",
) -> str:
    error_block = (
        f'<div class="error">{error}</div>' if error else ""
    )
    return _PAGE_TEMPLATE.format(
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
        client_id=client_id,
        state=state,
        scope=scope,
        resource=resource,
        error_block=error_block,
    )


@router.get("/oauth/login", response_class=HTMLResponse)
async def login_get(request: Request) -> str:
    """Render the password form, forwarding all OAuth params as hidden inputs."""
    p = request.query_params
    return _render_login(
        code_challenge=p.get("code_challenge", ""),
        redirect_uri=p.get("redirect_uri", ""),
        redirect_uri_provided_explicitly=p.get("redirect_uri_provided_explicitly", "1"),
        client_id=p.get("client_id", ""),
        state=p.get("state", ""),
        scope=p.get("scope", ""),
        resource=p.get("resource", ""),
    )


@router.post("/oauth/login", response_class=HTMLResponse)
async def login_post(
    password: str = Form(default=""),
    code_challenge: str = Form(default=""),
    redirect_uri: str = Form(default=""),
    redirect_uri_provided_explicitly: str = Form(default="1"),
    client_id: str = Form(default=""),
    state: str = Form(default=""),
    scope: str = Form(default=""),
    resource: str = Form(default=""),
) -> HTMLResponse:
    """
    Validate the password and complete the authorization code flow.

    On success: create an auth code, redirect to redirect_uri?code=...&state=...
    On failure: re-render the form with a generic error (C9 — no oracle for
    which field was wrong).
    """
    expected = os.getenv("ANTON_LOGIN_PASSWORD", "").strip()
    # Refuse entirely if the password is unconfigured.
    if not expected:
        return HTMLResponse(
            _render_login(
                code_challenge=code_challenge,
                redirect_uri=redirect_uri,
                redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
                client_id=client_id,
                state=state,
                scope=scope,
                resource=resource,
                error="Login is not configured on this server.",
            )
        )

    if not secrets.compare_digest(password.encode(), expected.encode()):
        return HTMLResponse(
            _render_login(
                code_challenge=code_challenge,
                redirect_uri=redirect_uri,
                redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
                client_id=client_id,
                state=state,
                scope=scope,
                resource=resource,
                error="Incorrect password.",
            ),
            status_code=401,
        )

    # Password correct — issue an auth code and redirect to the client.
    code = create_auth_code(
        client_id=client_id,
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        redirect_uri_provided_explicitly=(redirect_uri_provided_explicitly == "1"),
        scopes=scope or None,
        resource=resource or None,
    )
    params: dict[str, str] = {"code": code}
    if state:
        params["state"] = state
    return RedirectResponse(
        url=redirect_uri + "?" + urlencode(params),
        status_code=302,
    )
