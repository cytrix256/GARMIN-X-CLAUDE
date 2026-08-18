"""One-time interactive Garmin login. Run this yourself.

    python login.py

Your password is typed directly into this process (hidden, via getpass),
used once to obtain OAuth tokens, and never written to disk or logged.
What is saved is the token bundle, which is what every other script uses.

Re-run this if the sync starts failing with an authentication error.
"""

from __future__ import annotations

import sys
from getpass import getpass

from garminconnect import Garmin, GarminConnectAuthenticationError

from garmin_auth import TOKEN_DIR, TOKEN_ENV, encode_tokens

SECRET_FILE = "garmin_token_b64.txt"


def main() -> int:
    print("Garmin Connect login")
    print("--------------------")
    print("Use the same email and password you use on connect.garmin.com.\n")

    email = input("Garmin email: ").strip()
    if not email:
        print("No email entered, aborting.")
        return 1

    password = getpass("Garmin password (hidden): ")
    if not password:
        print("No password entered, aborting.")
        return 1

    client = Garmin(
        email,
        password,
        prompt_mfa=lambda: input("MFA code from your email/authenticator: ").strip(),
    )

    print("\nSigning in...")
    try:
        client.login()
    except GarminConnectAuthenticationError as exc:
        print(f"\nLogin rejected by Garmin: {exc}")
        print("Check the email/password, and complete any MFA prompt.")
        return 1
    except Exception as exc:
        print(f"\nLogin failed: {exc}")
        return 1

    # Drop the password from memory as soon as it is no longer needed.
    del password
    client.password = None

    name = client.get_full_name()
    print(f"Connected as: {name}")

    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    client.client.dump(str(TOKEN_DIR))
    print(f"Tokens saved to: {TOKEN_DIR.resolve()}")

    encoded = encode_tokens(client.client.dumps())
    with open(SECRET_FILE, "w", encoding="utf-8") as fh:
        fh.write(encoded)

    print(f"\nCI secret written to: {SECRET_FILE}")
    print(f"  Add its contents as the repository secret {TOKEN_ENV}")
    print("  (GitHub -> Settings -> Secrets and variables -> Actions -> New secret)")
    print(f"  Then delete {SECRET_FILE}. It is already in .gitignore.")
    print("\nVerify everything works with:  python fetch_garmin_data.py --days 7")
    return 0


if __name__ == "__main__":
    sys.exit(main())
