"""Adapters: one per database (P37). Each reads one publisher's format whole and returns a dataset in the common
format, with a report of every loss and its reason; nothing downstream of an adapter knows that format.

An adapter is pure: `ingest(bytes, ...) -> (name, tables, report)`, or layers for geodata. Fetching, locking and
writing belong to `athena.ingest`, which reads the project's own `sources.toml` and `sources.lock`.
"""
