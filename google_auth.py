"""Shared Google sign-in for Gmail and Calendar. Read-only scopes only."""
from pathlib import Path

BASE = Path(__file__).parent
CREDENTIALS_FILE = BASE / "credentials.json"
TOKEN_FILE = BASE / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


class SetupNeeded(Exception):
    """Raised when the user still has to connect their Google account."""


def get_credentials():
    if not CREDENTIALS_FILE.exists() and not TOKEN_FILE.exists():
        raise SetupNeeded(
            "Google is not connected yet. Create credentials.json in Google Cloud Console "
            "and run: python authorize.py"
        )
    if not TOKEN_FILE.exists():
        raise SetupNeeded("Sign in to Google once by running: python authorize.py")

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
            return creds
        except Exception:
            pass
    raise SetupNeeded(
        "Your Google sign-in has expired. Run python authorize.py again "
        "(see README, 'Connect Google', for how to stop this from expiring weekly)."
    )
