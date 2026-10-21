"""Wikidata's structured facts about the African Union's member states, read whole for those states (CC0).

Two queries to the public query service, each hash-locked through athena.fetch like any download:
- MEMBERSHIP: every "member of" (P463) statement of every current AU member state, with its start and end dates
  where Wikidata records them. Nothing is filtered by the kind of organisation: which groupings to show is a
  project's choice.
- ATTRIBUTES: the official languages (P37), currencies (P38), basic form of government (P122) and driving side
  (P1622), each as Wikidata's best-ranked ("truthy") statements, so a currency since replaced, ranked below the
  current one, is left out; and whether Wikidata classes the state as a landlocked country (Q123480) or an island
  country (Q112099).

Wikidata is uneven. Its membership statements are complete for some organisations (ECOWAS, with dates) and missing
for others (no COMESA or IGAD statements on 2026-10-20), so the report counts the members of each organisation, and
a project checks any list it relies on against its own.

All structured data on Wikidata is CC0 (Wikidata:Licensing, read 2026-10-18).
"""

from __future__ import annotations

import json

import pandas as pd

from athena import commons

STATES = """  ?state p:P463 ?au . ?au ps:P463 wd:Q7159 . FILTER NOT EXISTS { ?au pq:P582 ?auEnd }
  ?state wdt:P298 ?iso3 ."""


def membership_query(edition: str) -> str:
    return f"""# Athena: the AU member states' memberships, edition {edition}
SELECT ?iso3 ?org ?orgLabel ?start ?end WHERE {{
{STATES}
  ?state p:P463 ?m . ?m ps:P463 ?org .
  OPTIONAL {{ ?m pq:P580 ?start }} OPTIONAL {{ ?m pq:P582 ?end }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def attributes_query(edition: str) -> str:
    return f"""# Athena: the AU member states' attributes, edition {edition}
SELECT ?iso3 ?property ?value ?valueLabel WHERE {{
{STATES}
  {{ ?state wdt:P37 ?value . BIND("P37" AS ?property) }}
  UNION {{ ?state wdt:P38 ?value . BIND("P38" AS ?property) }}
  UNION {{ ?state wdt:P122 ?value . BIND("P122" AS ?property) }}
  UNION {{ ?state wdt:P1622 ?value . BIND("P1622" AS ?property) }}
  UNION {{ ?state wdt:P31 ?value . BIND("P31" AS ?property) FILTER(?value IN (wd:Q123480, wd:Q112099)) }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _day(stamp: str | None) -> str:
    return stamp[:10] if stamp else ""


def ingest(membership: bytes, attributes: bytes, edition: str) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    """The dataset's name, its two tables and the report. A row without its state or organisation stops the
    ingest; exact repeats (one statement reached twice) are kept once."""
    name = f"wikidata-states-{edition}"
    rows = commons.bindings(json.loads(membership))
    if any(not r.get("iso3") or not r.get("org") for r in rows):
        raise ValueError("a membership row lacks its state or its organisation")
    members = pd.DataFrame([{"iso3": r["iso3"], "org": _qid(r["org"]), "org_label": r.get("orgLabel", ""),
                             "start": _day(r.get("start")), "end": _day(r.get("end"))} for r in rows])
    members = members.drop_duplicates().sort_values(["org", "iso3", "start"], ignore_index=True)
    rows = commons.bindings(json.loads(attributes))
    if any(not r.get("iso3") or not r.get("property") or not r.get("value") for r in rows):
        raise ValueError("an attribute row lacks its state, property or value")
    facts = pd.DataFrame([{"iso3": r["iso3"], "property": r["property"], "value": _qid(r["value"]),
                           "value_label": r.get("valueLabel", "")} for r in rows])
    facts = facts.drop_duplicates().sort_values(["iso3", "property", "value"], ignore_index=True)
    current = members[members["end"] == ""]
    counts = current.groupby(["org", "org_label"])["iso3"].nunique().sort_values(ascending=False)
    report = [f"{name}: Wikidata, the African Union member states, query edition {edition}",
              f"  {len(members):,} membership statements ({len(current):,} current) of {members['iso3'].nunique()} "
              f"states in {members['org'].nunique()} organisations",
              f"  {len(facts):,} attribute statements: " + ", ".join(
                  f"{p} {n}" for p, n in facts["property"].value_counts().sort_index().items()),
              "  current members per organisation (2 or more):"]
    report += [f"    {n:3d}  {label} ({org})" for (org, label), n in counts.items() if n >= 2]
    return name, {"membership": members, "attributes": facts}, report
