"""Shared Garmin Connect authentication.

Two ways to get an authenticated client, in priority order:

1. GARMIN_TOKENS_B64 environment variable (base64 of client.dumps()).
   This is what GitHub Actions uses -- no password ever reaches CI.
2. A local token directory (default ./tokens, override with GARMINTOKENS).
   Created by running login.py once on your own machine.

Passwords are never read here. Only login.py touches a password, and it
reads it straight from the keyboard via getpass.
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from garminconnect import Garmin

TOKEN_DIR = Path(os.getenv("GARMINTOKENS", "tokens")).expanduser()
TOKEN_ENV = "GARMIN_TOKENS_B64"


def encode_tokens(client_state: str) -> str:
    """Base64-encode a client.dumps() string for storage in a CI secret."""
    return base64.b64encode(client_state.encode("utf-8")).decode("ascii")


def decode_tokens(encoded: str) -> str:
    """Reverse of encode_tokens. Tolerates whitespace/newlines from secret UIs."""
    cleaned = "".join(encoded.split())
    try:
        return base64.b64decode(cleaned, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(
            f"{TOKEN_ENV} is not valid base64-encoded token JSON. "
            "Re-run login.py and copy the whole one-line value."
        ) from exc


def authenticate() -> Garmin:
    """Return a logged-in Garmin client, or raise with a fixable message."""
    encoded = os.getenv(TOKEN_ENV)
    if encoded:
        client = Garmin()
        # login() accepts inline token JSON, and crucially also loads the
        # profile. Calling client.loads() directly skips that, leaving
        # display_name unset -- which fails every endpoint that puts the
        # display name in its URL, with "Display name is not set".
        client.login(decode_tokens(encoded))
        _assert_live(client, source=f"${TOKEN_ENV}")
        return client

    if TOKEN_DIR.is_dir():
        client = Garmin()
        client.login(str(TOKEN_DIR))
        _assert_live(client, source=str(TOKEN_DIR))
        return client

    raise RuntimeError(
        "No Garmin credentials found.\n"
        f"  Locally: run `python login.py` to create {TOKEN_DIR}/\n"
        f"  In CI:   set the {TOKEN_ENV} repository secret."
    )


def _assert_live(client: Garmin, source: str) -> None:
    """Fail loudly now rather than mid-sync if the session is not usable."""
    try:
        client.get_full_name()
    except Exception as exc:
        raise RuntimeError(
            f"Garmin token from {source} was rejected ({exc}).\n"
            "Tokens expire roughly yearly, or when you change your Garmin "
            "password. Re-run `python login.py` and update the secret."
        ) from exc

    # Without display_name most endpoints fail one by one while the sync
    # still exits 0 -- a green run that quietly collected almost nothing.
    if not getattr(client, "display_name", None):
        raise RuntimeError(
            f"Authenticated from {source}, but the Garmin profile did not "
            "load (display_name is unset). Most endpoints would fail with "
            "'Display name is not set'. Re-run `python login.py`."
        )
