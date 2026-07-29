# Dotfiles repository

Apply these rules only when dotfiles is the active repository. A global
guidance symlink resolving here does not make dotfiles active.

Treat this repository as a small portable terminal profile with explicit,
opt-in desktop overlays:

- `.zshenv`: environment for every Zsh invocation; keeps `~/.local/bin` on
  `PATH` in non-interactive shells.
- `.zshrc`: interactive Zsh; Oh My Zsh is optional.
- `.tmux.conf`: portable tmux defaults and bindings.
- `install.sh`: backs up conflicts, links the portable core, and deploys
  version-gated desktop manifests as regular files.
- `profiles/`: curated common and semantic host layers for supported desktop
  profiles.
- `tests/`: isolated installer and safety checks.
- `README.md`: setup, synchronization, and local overrides.

Exclude AIQ runtime state, credentials, private host identity, generated
state, caches, restored duplicates, and unmodified vendor trees. Put
machine-specific shell configuration in `~/.zshrc.local`. Put reviewed
machine-specific desktop values in a semantic host layer that does not expose
a hostname.

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
- When adding a portable core file, update `managed_links` and `README.md`.
- Keep every desktop destination in a strict manifest. Deploy desktop payloads
  as regular files only after exact profile-version and schema checks; never
  symlink a mutable vendor sandbox into Git.
- When changing a desktop payload, keep manifest-to-payload equality, the
  `common/` and semantic `hosts/` split, provenance, license boundaries,
  `README.md`, and isolated tests current.
- Treat the Git payload as authoritative. Do not capture deployed, generated,
  or inline-edited vendor files automatically.
- Preserve the `common/` and semantic `hosts/` split. Record upstream identity,
  modifications, and license boundaries for derived configuration.
- Do not edit outside this repository during routine work or verification
  unless the user requests installation or managed-file verification.

## Guidance maintenance

A guidance fix made off `main` is incomplete until its commits are integrated
into local `main`, the temporary branch and any temporary worktree or directory
are removed, and the checkout is clean on `main`. Never add AIQ runtime state
or history while performing that work. Push only with user authority.

## Verification

Run the smallest relevant checks. For repository-wide profile changes:

```sh
sh -n install.sh
sh -n tests/install.sh
zsh -n .zshrc
tmux_socket="dotfiles-check-$$"
tmux -L "$tmux_socket" -f "$PWD/.tmux.conf" new-session -d
tmux -L "$tmux_socket" kill-server

install_test_home=$(mktemp -d)
env HOME="$install_test_home" ./install.sh
env HOME="$install_test_home" ./install.sh --check

./tests/install.sh
jq -e . profiles/ml4w/*/common/.config/waybar/*.json \
  profiles/ml4w/*/common/.config/waybar/themes/*/config-custom
```

Use only a temporary home and remove it afterward. Report unavailable checks
instead of installing tools or claiming success. The isolated profile test must
also enforce exact manifest-to-payload equality. Run a live desktop `--check`
only when the user authorized verification of that managed profile. For
documentation-only changes, verify structure, commands, links, and filenames.

Done means the requested behavior works; relevant checks pass or skips are
reported; documentation is current; the diff has no unrelated changes,
secrets, or generated artifacts; and the final report states the result and
verification.
