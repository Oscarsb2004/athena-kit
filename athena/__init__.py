"""athena-kit: the shared, public parts of Athena that anyone needs to run a project built with it (P108).

Published statistics in one common format, fetched once and hash-locked, with the store, the geodata store, the
shared section templates and figures, Wikimedia Commons, one adapter per database (`athena.adapters`), the runner
that ingests a project's own sources (`athena.ingest`), and the component standard and its checker
(`athena.component`, `athena.components`). Each project lives in its own repository and installs this package;
Athena's own system (the library tooling, the Stewards, the agents) is private and builds on it.

PolyForm Noncommercial 1.0.0; see LICENSE.md and NOTICE.
"""
