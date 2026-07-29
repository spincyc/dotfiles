# Guidance maintenance

Apply this document when editing files under the guidance root, whichever
repository is active.

- Guidance edits target the resolved guidance root; their intended local
  target, per completion in `00-core.md`, is dotfiles local `main` even when
  another repository is active.
- After editing `AI_GUIDANCE.md`, a numbered document, or a bootstrap entry
  point, run `make verify` from the guidance root. `AI_GUIDANCE.md` is gated
  by a word budget and an index parity check; keep it a small loader.
- Keep each rule in its owning document and cross-reference instead of
  copying. Authority, mutation, and completion rules stay owned by
  `00-core.md`; runtime-state rules by `10-journal.md`.
