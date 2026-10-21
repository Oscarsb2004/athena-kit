"""Glottolog's catalogue of the world's languages, read from its CLDF release (CC BY 4.0).

Glottolog lists every languoid (family, language or dialect) with its family, macroarea, coordinates and the
countries it is spoken in (ISO 3166-1 alpha-2 codes), and assesses each language twice:
- AES, the agglomerated endangerment status, from "not endangered" to "extinct" (compiled from EGIDS, UNESCO and
  ElCat);
- MED, the most extensive description, from "long grammar" to "wordlist or less".

The CLDF tables read are languages, values, codes and parameters; the alternative names (names.csv), the trees and
the bibliography are not read, and the report says so. Glottolog counts languages; it has no speaker numbers.

Cite as: Hammarström, Harald & Forkel, Robert & Haspelmath, Martin & Bank, Sebastian. 2026. Glottolog 5.3. Leipzig:
Max Planck Institute for Evolutionary Anthropology. CC BY 4.0 (the release's LICENSE and README, read 2026-10-20).
"""

from __future__ import annotations

import io

import pandas as pd

TABLES = ("languages", "values", "codes", "parameters")
LANGUAGE_COLUMNS = ["ID", "Name", "Level", "Family_ID", "Macroarea", "Latitude", "Longitude", "ISO639P3code",
                    "Countries", "Is_Isolate"]
ASSESSED = ("aes", "med", "category")
NOT_READ = ["names.csv (alternative names)", "classification.nex and trees.csv", "sources.bib (bibliography)"]


def ingest(files: dict[str, bytes], edition: str) -> tuple[str, dict[str, pd.DataFrame], list[str]]:
    """The dataset's name, one table of languoids with their assessments, and the report. A missing table or column
    stops the ingest, as does an assessment whose code the code table does not define."""
    name = f"glottolog-{edition}"
    missing = sorted(set(TABLES) - set(files))
    if missing:
        raise ValueError(f"missing CLDF tables: {missing}")
    t = {k: pd.read_csv(io.BytesIO(files[k]), dtype=str, keep_default_na=False) for k in TABLES}
    absent = sorted(set(LANGUAGE_COLUMNS) - set(t["languages"].columns))
    if absent:
        raise ValueError(f"languages.csv lacks {absent}")
    lang = t["languages"][LANGUAGE_COLUMNS].rename(columns=str.lower).rename(columns={
        "id": "glottocode", "family_id": "family", "iso639p3code": "iso639_3", "latitude": "lat", "longitude": "lon"})
    families = dict(zip(t["languages"]["ID"], t["languages"]["Name"]))
    lang.insert(4, "family_name", lang["family"].map(families).fillna(""))
    codes = dict(zip(t["codes"]["ID"], t["codes"]["Name"]))
    for parameter in ASSESSED:
        rows = t["values"][t["values"]["Parameter_ID"] == parameter]
        unknown = sorted(set(rows["Code_ID"]) - set(codes) - {""})
        if unknown:
            raise ValueError(f"{parameter}: codes not in codes.csv: {unknown[:5]}")
        lang[parameter] = lang["glottocode"].map(dict(zip(rows["Language_ID"], rows["Code_ID"].map(codes)))).fillna("")
    languages = lang[lang["level"] == "language"]
    report = [f"{name}: Glottolog {edition}, the CLDF release",
              f"  {len(lang):,} languoids, {len(languages):,} of them languages, in "
              f"{lang.loc[lang['level'] == 'family', 'glottocode'].nunique():,} family-level groupings",
              f"  languages with countries: {(languages['countries'] != '').sum():,}; with an endangerment status: "
              f"{(languages['aes'] != '').sum():,}; with a description status: {(languages['med'] != '').sum():,}",
              f"  in the Africa macroarea: {(languages['macroarea'] == 'Africa').sum():,} languages",
              f"  not read: {'; '.join(NOT_READ)}"]
    return name, {"languoids": lang.reset_index(drop=True)}, report
