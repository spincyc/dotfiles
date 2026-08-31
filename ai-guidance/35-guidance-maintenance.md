# Guidance maintenance

Apply these rules when editing the guidance file set — `AI_GUIDANCE.md`,
`ai-guidance/`, or a bootstrap entry point — whichever repository is active.

- Guidance edits target the resolved guidance root; their intended local
  target, per completion in `00-core.md`, is dotfiles local `main` even when
  another repository is active.
- After editing `AI_GUIDANCE.md`, a numbered document, or a bootstrap entry
  point, run `make verify` from the guidance root. For documentation-only
  edits, `make verify-guidance` is the cheap subset: budget, bootstrap,
  cross-reference, index, recovery-contract, and relay-contract checks,
  without the tmux and temp-home battery.
- The loader budget has two failing tiers: 250 words is the hard cap, and
  225 already fails with "discuss simplification" — the effective ceiling is
  224. Additions to `AI_GUIDANCE.md` therefore need matching trims or an
  owner conversation; keep it a small loader.
- The final report of any guidance-editing task states whether the commit
  reached `origin` — for example "guidance commit <sha> is local-only; push
  to propagate".
- Running sessions hold session-start snapshots of the guidance. After
  editing, re-read the changed files before relying on them, and expect
  other live sessions to stay stale until restarted.
- Keep each rule in its owning document and cross-reference instead of
  copying. Authority, mutation, and completion rules stay owned by
  `00-core.md`; runtime-state rules by `10-journal.md`.
