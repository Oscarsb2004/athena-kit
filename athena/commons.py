"""Wikidata and Wikimedia Commons: places from Wikidata's query service, and photographs from Commons with their
licences. Shared by the ASI's Wonders and the Canada atlas, whose shell this was (P42: a second project needs it).

Wikidata's structured data is CC0 (Wikidata:Licensing, read 2026-10-18). Every Commons file carries its own licence;
a file without a stated licence is refused, never assumed free. Requests go through `athena.fetch`, whose
User-Agent names the project and a contact, as Wikimedia's User-Agent policy asks.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlencode

SPARQL = "https://query.wikidata.org/sparql"
COMMONS = "https://commons.wikimedia.org/w/api.php"
FIELDS = ("LicenseShortName", "LicenseUrl", "Artist", "Restrictions", "Credit")


class MediaError(ValueError):
    """Commons did not return a usable record for a requested file."""


def strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def sparql_url(query: str) -> str:
    """A Wikidata query as one GET address; the query's own text (with its edition comment) makes it unique."""
    return SPARQL + "?" + urlencode({"format": "json", "query": query})


def bindings(response: dict[str, Any]) -> list[dict[str, str]]:
    """A SPARQL JSON result as rows of plain strings."""
    return [{k: v["value"] for k, v in row.items()} for row in response["results"]["bindings"]]


def category_url(category: str, limit: int = 20) -> str:
    """The files in a Commons category, in the category's own order."""
    return COMMONS + "?" + urlencode({"action": "query", "format": "json", "list": "categorymembers",
                                      "cmtitle": f"Category:{category}", "cmtype": "file", "cmlimit": limit})


def category_files(response: dict[str, Any]) -> list[str]:
    return [m["title"] for m in response.get("query", {}).get("categorymembers", [])]


def imageinfo_url(titles: list[str], width: int) -> str:
    """One Commons request for up to 50 files: URLs, a rendering at `width`, and the licence metadata."""
    if len(titles) > 50:
        raise MediaError("the Commons API takes at most 50 titles a request")
    return COMMONS + "?" + urlencode({
        "action": "query", "format": "json", "titles": "|".join(titles), "prop": "imageinfo",
        "iiprop": "url|sha1|extmetadata", "iiurlwidth": width, "iiextmetadatafilter": "|".join(FIELDS)})


def records(response: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Each file's record, keyed by the title as requested, and the files refused with the reason."""
    query = response.get("query") or {}
    back = {n["to"]: n["from"] for n in query.get("normalized", [])}  # Commons normalises underscores and case
    kept, refused = {}, {}
    for page in (query.get("pages") or {}).values():
        title = back.get(page.get("title"), page.get("title"))
        if "missing" in page or not page.get("imageinfo"):
            refused[title] = "no such file"
            continue
        info = page["imageinfo"][0]
        meta = {k: strip_tags(str((info.get("extmetadata") or {}).get(k, {}).get("value", ""))) for k in FIELDS}
        if not meta["LicenseShortName"]:
            refused[title] = "no stated licence"
        elif not info.get("thumburl"):
            refused[title] = "no rendering"
        else:
            kept[title] = {"title": title, "page_url": info.get("descriptionurl", ""),
                           "rendering_url": info["thumburl"], "licence": meta["LicenseShortName"],
                           "licence_url": meta["LicenseUrl"], "artist": meta["Artist"], "credit": meta["Credit"],
                           "restrictions": [r for r in meta["Restrictions"].split("|") if r]}
    return kept, refused
