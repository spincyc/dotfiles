# Global AI contributor guidance

Canonical personal instructions for AI agents. Higher-authority system and
developer instructions and narrower repository-local instructions remain
controlling.

## Resolve and load

Resolve this file through every symlink. Treat the directory containing the
resolved `AI_GUIDANCE.md` as the guidance root. A symlink into the dotfiles
checkout does not make dotfiles the active repository.

Read applicable documents completely and in numeric order:

1. [`00-core.md`](ai-guidance/00-core.md) — always.
2. [`10-journal.md`](ai-guidance/10-journal.md) — always.
3. [`15-tool-making.md`](ai-guidance/15-tool-making.md) — when the active
   repository has a root `tmt.json` or tmt is available.
4. [`20-sub-agent-scheduling.md`](ai-guidance/20-sub-agent-scheduling.md) —
   before the first delegation decision.
5. [`30-collaboration.md`](ai-guidance/30-collaboration.md) — always.
6. [`35-guidance-maintenance.md`](ai-guidance/35-guidance-maintenance.md) —
   always.
7. [`40-dotfiles-repository.md`](ai-guidance/40-dotfiles-repository.md) — only
   when dotfiles is the active repository.

## Availability

A CLI tool is available when `command -v` finds it or
`$HOME/.local/bin/<tool>` is executable; after a `PATH` miss, keep invoking
the absolute path. Sub-agent and harness-tool availability follow the
session's tool roster: a tool listed by name counts, even when its schema
loads on demand.

These documents are additive within their declared scopes. Numeric order
controls reading, not precedence; contradiction disposition is owned by
`00-core.md`.

If an applicable document is unavailable, state the limitation and continue
only when higher-authority instructions and the readable guidance leave a
safe, unambiguous path.
