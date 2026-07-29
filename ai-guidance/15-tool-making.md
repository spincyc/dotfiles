# Tool making

Use `tmt` when it is available (Availability, `AI_GUIDANCE.md`). Listed tools
run as `tools/<id>` without tmt.

- Before writing any script, read the repository's `tmt.json` if present and
  prefer a listed tool over re-deriving. Session-start `tmt context` output
  counts as a current read until the repository changes or you alter the
  registry.
- After deriving anything repeatable, record it with `tmt note <slug>`
  (add `--note` for context). Noting is cheap; do not pre-filter by estimated
  cost. When the reported count reaches 2, scaffold with `tmt new <id>`
  (Python by default) and paste the derived logic.
- Prefer editing the nearest existing tool over creating a near-duplicate.
  Before building, check `~/git/tmt-lib` and prefer `tmt vendor` for a tool
  already stabilized elsewhere.
- `tmt.json` is a committed artifact: do not run `tmt init` — or `tmt vendor`,
  which writes the registry — in a repository lacking one without user
  authority. The loop still runs registry-less: `tmt note` works, and at the
  threshold propose `tmt init` to the user.
- Never hand-edit the `stage` field; `tmt stage <id> stable` is the only
  promotion and runs the full stable battery. Other entry fields are
  maintained by hand, and every edit must leave `tmt check` green — keep
  `tmt check` in the repository's verify target. Harden a tool with real
  tests and the `stable` stage before other tools depend on it.
- `aiq` remains authoritative for work state. Record candidate events only
  via `tmt note` and read them via `tmt candidates`; hand-crafted ingest
  events are silently uncounted.
