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
2. [`10-journal.md`](ai-guidance/10-journal.md) — when the active repository
   contains `.journal/README.md` or the task changes journal guidance.
3. [`20-sub-agent-scheduling.md`](ai-guidance/20-sub-agent-scheduling.md) —
   when sub-agent tools are available.
4. [`30-collaboration.md`](ai-guidance/30-collaboration.md) — always.
5. [`40-dotfiles-repository.md`](ai-guidance/40-dotfiles-repository.md) — only
   when dotfiles is the active repository.

These documents are additive within their declared scopes. Numeric order
controls reading, not precedence; treat a contradiction as a guidance defect,
not as an implicit override.

If an applicable document is unavailable, state the limitation and continue
only when higher-authority instructions and the readable guidance leave a
safe, unambiguous path.
