"""Fetch once, keep forever.

Every response is kept on disk by requests-cache and never expires, so a source is downloaded once. A lock file
records each URL's SHA-256 and is committed: a source whose bytes change is refused, never silently used. TLS is
always verified. A `file:` address is a path inside the project (the folder that holds its lock), read from disk and
locked like any other.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import requests_cache

STORE = Path(os.environ.get("ATHENA_STORE", "C:/AthenaStore"))
WAYBACK = "https://web.archive.org/web/{stamp}id_/{url}"
# Names the project and a contact, as Wikimedia's User-Agent policy asks of every script (read 2026-10-18).
USER_AGENT = "athena-bot/0.2 (https://github.com/Oscarsb2004/athena-core; research replication)"


class SourceChanged(RuntimeError):
    pass


def cached_session(store: Path = STORE) -> requests_cache.CachedSession:
    # decode_content=False keeps each body exactly as received; the default re-encodes JSON, changing its bytes.
    session = requests_cache.CachedSession(str(store / "http"), backend="filesystem", decode_content=False,
                                           expire_after=requests_cache.NEVER_EXPIRE, allowable_codes=(200,))
    session.headers["User-Agent"] = USER_AGENT
    return session


class Fetcher:
    """Gets URLs through a cached session and holds each one to the hash in the lock file."""

    def __init__(self, lock: Path, session=None, base: Path | None = None):
        self.lock_path = lock
        self.base = Path(base) if base is not None else Path(lock).parent  # where `file:` addresses start
        self.lock: dict[str, str] = json.loads(lock.read_text(encoding="utf-8")) if lock.exists() else {}
        self.session = session if session is not None else cached_session()

    def get(self, url: str) -> bytes:
        if url.startswith("file:"):
            content = (self.base / url.removeprefix("file:")).read_bytes()
        else:
            response = self.session.get(url, timeout=120)
            response.raise_for_status()
            content = response.content
        digest = hashlib.sha256(content).hexdigest()
        locked = self.lock.get(url)
        if locked is None:
            self.lock[url] = digest
            self.lock_path.write_text(json.dumps(self.lock, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                      newline="\n")
        elif locked != digest:
            raise SourceChanged(f"{url}: sha256 is {digest}, the lock says {locked}")
        return content
