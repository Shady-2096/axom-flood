# Contributing

Run `uv sync --extra dev --locked`, `uv run ruff check .`, and `uv run pytest`
before proposing a parser change.

Public-source safety rules:

- preserve raw source payloads by content hash;
- never overwrite a prior revision or extractor artifact;
- treat missing and stale data explicitly, without interpolation;
- keep source URLs and timestamps with derived output;
- route ambiguous camp/school matches to review;
- do not scrape authenticated or undocumented private endpoints;
- do not describe translated data as an official warning.

When a source layout changes, add a minimized fixture test and bump the
extractor or schema version if the emitted contract changes.
