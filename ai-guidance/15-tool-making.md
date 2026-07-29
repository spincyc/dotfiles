# Tool making

Use `tmt` when it is available.

- Before writing any script, read the repository's `tmt.json` if present and
  prefer a listed tool over re-deriving.
- When a derivation is likely to recur, or costs more than roughly 500 tokens
  and has a deterministic answer, record it with `tmt note <slug>`.
- On a second occurrence, build the tool with `tmt new` (Python by default).
- Prefer editing the nearest existing tool over creating a near-duplicate.
- Harden a tool — tests and the `stable` stage — before other tools depend on
  it.
- `aiq` remains authoritative for work state; tmt candidate events flow
  through `aiq ingest`.
