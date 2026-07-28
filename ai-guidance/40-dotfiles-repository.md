# Dotfiles repository

Apply these rules only when dotfiles is the active repository. A global
guidance symlink resolving here does not make dotfiles active.

Treat this repository as a small terminal profile:

- `.zshrc`: interactive Zsh; Oh My Zsh is optional.
- `.tmux.conf`: portable tmux defaults and bindings.
- `install.sh`: backs up conflicts and links managed files.
- `README.md`: setup, synchronization, and local overrides.

Exclude `.journal/`, desktop settings, credentials, host-specific values, and
generated files. Put machine-specific shell configuration in `~/.zshrc.local`.

## Change rules

- Inspect relevant files and Git state; preserve unrelated user changes.
- Keep changes small, portable, optional-dependency-friendly, and removable.
  Add no framework or manager unless required.
- Preserve installer backups and fast-forward-only updates.
- Document changes to commands, dependencies, managed files, bindings, or
  local configuration.
- Keep `install.sh` POSIX `sh` with `set -eu`; quote expansions and use `--`
  before paths when supported.
- Keep `.zshrc` valid Zsh and `.tmux.conf` valid tmux configuration. Prefer
  feature detection and fallbacks.
- Use two-space shell indentation and descriptive snake_case names.
- When adding a managed file, update `managed_links` and `README.md`.
- Do not edit outside this repository during routine work or verification
  unless the user requests installation or managed-file verification.

## Guidance maintenance

A guidance fix made off `main` is incomplete until its commits are integrated
into local `main`, the temporary branch and any temporary worktree or directory
are removed, and the checkout is clean on `main`. Never add `.journal/` files
or history while performing that work. Push only with user authority.

## Verification

Run the smallest relevant checks. For repository-wide profile changes:

```sh
sh -n install.sh
zsh -n .zshrc
tmux_socket="dotfiles-check-$$"
tmux -L "$tmux_socket" -f "$PWD/.tmux.conf" new-session -d
tmux -L "$tmux_socket" kill-server

install_test_home=$(mktemp -d)
env HOME="$install_test_home" ./install.sh
env HOME="$install_test_home" ./install.sh --check
```

Use only a temporary home and remove it afterward. Report unavailable checks
instead of installing tools or claiming success. For documentation-only
changes, verify structure, commands, links, and filenames.

Done means the requested behavior works; relevant checks pass or skips are
reported; documentation is current; the diff has no unrelated changes,
secrets, or generated artifacts; and the final report states the result and
verification.
