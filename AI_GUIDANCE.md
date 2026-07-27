# AI contributor guidance

Canonical instructions for every AI agent in this repository. Tool-specific
files must point here, not duplicate it.

## Required workflow

Before repository work, read [`.journal/README.md`](.journal/README.md) and:

1. Verify the repository, branch, HEAD, remotes, and working tree.
2. Create an agent-instance UUID. Read journal state, queue, active tasks,
   relevant history, and leases.
3. Durably classify and enrich each user message before acting. Queue new work;
   do not interrupt active work unless explicitly directed or continuation is
   unsafe or invalid.
4. Preserve history with immutable events and decisions. Supersede explicitly;
   never silently rewrite a decision.
5. Re-read durable state at recovery and scheduling boundaries, before
   checkpoints, after unexpected Git changes, and before completion or yield.
6. Make all safe progress using documented, reversible assumptions. Continue
   runnable tasks when another task blocks.
7. Commit journal and attributable implementation checkpoints locally. Do not
   push, change branches, merge, rebase, or rewrite history without authority.

Run `python3 .journal/bin/journal.py validate` before journal commits.

## Collaboration

Be candid and evidence-oriented. Optimize for the result, not agreement.

- Test proposals for material risks, contradictions, costs, and stronger
  alternatives. State consequential concerns plainly with reasons.
- Do not flatter, reflexively agree, over-reassure, manufacture objections, or
  perform opposition.
- Distinguish fact, inference, uncertainty, and preference. Match criticism to
  the evidence and stakes.
- Make criticism useful: explain consequences and recommend an alternative.
- Preserve momentum. Use a superior safe, reversible approach when it retains
  the requested outcome; document why and proceed.
- Request direction when an alternative materially changes outcome, scope,
  risk, or external consequences.

## Repository

This is a small terminal profile:

- `.zshrc`: interactive Zsh; Oh My Zsh is optional.
- `.tmux.conf`: portable tmux defaults and bindings.
- `install.sh`: backs up conflicts and links managed files.
- `README.md`: setup, synchronization, and local overrides.

Exclude desktop settings, credentials, host-specific values, and generated
files. Put machine-specific shell configuration in `~/.zshrc.local`.

## Change rules

- Inspect relevant files and `git status`; preserve unrelated user changes.
- Keep changes small, portable, optional-dependency-friendly, and removable.
  Add no framework or manager unless required.
- Never commit secrets, identity data, shell history, or machine-specific
  paths.
- Preserve installer backups and fast-forward-only updates.
- Document changes to commands, dependencies, managed files, bindings, or
  local configuration.
- Keep `install.sh` POSIX `sh` with `set -eu`; quote expansions and use `--`
  before paths when supported.
- Keep `.zshrc` valid Zsh and `.tmux.conf` valid tmux configuration. Prefer
  feature detection and fallbacks.
- Use two-space shell indentation, descriptive snake_case names, and comments
  that explain intent.
- When adding a managed dotfile, update `managed_files` and `README.md`.
- Do not edit outside the repository during routine work or verification.

## Verification

Run the smallest relevant checks. For repository-wide changes:

```sh
sh -n install.sh
zsh -n .zshrc
tmux_socket="dotfiles-check-$$"
tmux -L "$tmux_socket" -f "$PWD/.tmux.conf" new-session -d
tmux -L "$tmux_socket" kill-server

test_home=$(mktemp -d)
HOME="$test_home" ./install.sh
HOME="$test_home" ./install.sh --check
```

Use only a temporary home; remove it afterward. Report unavailable checks
instead of installing tools or claiming success. For documentation-only
changes, verify structure, commands, links, and filenames.

Done means: requested behavior works; relevant checks pass or skips are
reported; user-facing documentation is current; the diff has no unrelated
changes, secrets, or generated artifacts; and the final report states the
result and verification.
