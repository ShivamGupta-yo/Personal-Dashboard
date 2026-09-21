"""Run once: python authorize.py
Opens your browser, asks you to approve read-only access to Gmail and Calendar,
and saves token.json next to this file. Nothing is sent anywhere except to Google."""
import os
import sys

from google_auth import CREDENTIALS_FILE, SCOPES, TOKEN_FILE


def main():
    if not CREDENTIALS_FILE.exists():
        sys.exit(
            "credentials.json not found.\n"
            "Create an OAuth client (type: Desktop app) in Google Cloud Console, download the JSON, "
            "and save it here as credentials.json. See README.md, section 'Connect Google'."
        )

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    TOKEN_FILE.write_text(creds.to_json())
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    print("Connected. token.json saved. You can now start the app with: python app.py")


if __name__ == "__main__":
    main()
