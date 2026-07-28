# Global AI contributor guidance

Canonical personal instructions for AI agents. Tool-specific files point here;
higher-authority system or developer instructions and narrower
repository-local instructions remain controlling.

## Resolve this guidance set

Resolve this file through every symlink. Treat the directory containing the
resolved `AI_GUIDANCE.md` as the guidance root, and load `ai-guidance/`
relative to that directory. A symlink into the dotfiles checkout does not make
dotfiles the active repository.

## Mandatory reading order

Before acting, read every document below completely and in numeric order.
Numeric prefixes define normative reading order, not merely display order.
Later documents specialize earlier ones only within their stated scope.

1. [`00-core.md`](ai-guidance/00-core.md) — authority, scope, and universal
   invariants.
2. [`10-journal.md`](ai-guidance/10-journal.md) — all durable journal
   behavior.
3. [`20-sub-agent-scheduling.md`](ai-guidance/20-sub-agent-scheduling.md) —
   delegation and parallel capacity.
4. [`30-collaboration.md`](ai-guidance/30-collaboration.md) — evidence,
   criticism, and decisions.
5. [`40-dotfiles-repository.md`](ai-guidance/40-dotfiles-repository.md) —
   dotfiles-specific rules and verification.

If a required document is unavailable or unreadable, state that limitation
and continue only when higher-authority instructions and the readable guidance
leave a safe, unambiguous path.
