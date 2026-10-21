"""Shared test helpers for athena-core: an offline session that serves bytes by address, so no test touches
the network. Each test builds its own synthetic files; no publisher content is kept in git.

The MDG project's fixtures (projects/mdg/tests/mdg_fixtures.py) import this session too.
"""

from __future__ import annotations


class Response:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


class Session:
    """Serves bytes by address, so tests never touch the network."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def get(self, url: str, timeout: float | None = None) -> Response:
        return Response(self.files[url])
