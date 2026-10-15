"""
Sign out everywhere from the command line (R9.2).

Revokes every browser session and every OAuth token/auth code. Use over SSH
when a phone is lost. Named bearer tokens (ANTON_TOKENS) are not affected.

    python -m app.scripts.sign_out_everywhere
"""
import argparse

from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.parse_args()
    load_dotenv()
    # Imported after load_dotenv so DATABASE_URL from .env is honoured.
    from app.services.auth_admin import sign_out_everywhere

    result = sign_out_everywhere(source="cli")
    print(f"Revoked {result.sessions_revoked} session(s) and "
          f"{result.oauth_tokens_revoked} OAuth token(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
