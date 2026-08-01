# Output contracts

- `asdma-bulletin.schema.json`: one versioned bulletin extraction. Extractor
  v7+ additionally requires Phase B impact aggregates, detailed infrastructure,
  structured extraction warnings, and field-level source provenance.
- `asdma-impact-validation.schema.json`: validator-v1 evidence, deterministic
  checks, failures, warnings, publication state, and allowed-field profile.
- `asdma-impact.schema.json`: one normalized, immutable public impact snapshot
  with source revision, validation evidence, and publication profile.
- `asdma-impact-pointer.schema.json`: the small mutable pointer to the newest
  validated public impact snapshot.
- `asdma-impact-history.schema.json`: the mutable revision index used for
  report history and comparison without listing a static directory.
- `camp-source-record.schema.json`: one raw camp row with source provenance.
- `gauge-snapshot.schema.json`: one gap-aware station snapshot.
- `locality.schema.json`: revenue-circle alert localities, review-gated Assamese
  names, manual river/topology gauge mappings, and null Phase 4 thresholds.
- `gauge-topology-decisions.schema.json`: one reviewed answer per circle to
  whether its gauge sits on water that reaches it. The only input that can mark
  a gauge mapping reviewed, and the only one that can leave a circle with no
  gauge on purpose.
- `village-search-index.schema.json`: Census village search records and
  confidence-labelled derived centre points.

The UDISE reference and camp-match CSVs use stable headers emitted by
`src/axom_flood/udise/ingest.py` and `src/axom_flood/udise/matcher.py`.
Review files are JSON containers containing the same match records filtered to
`medium` and `unverified`.

All JSON outputs carry `schema_version`. Additive fields require documentation;
breaking changes require a schema-version bump and coexistence with earlier
immutable artifacts.
