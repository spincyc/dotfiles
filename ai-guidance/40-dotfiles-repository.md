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
- `AI_GUIDANCE.md`, `ai-guidance/`, and the bootstrap entry points
  (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`):
  the guidance root; bootstrap files defer to `AI_GUIDANCE.md`.
- `tools/`, `Makefile`: repository verification; `make verify` is the
  authoritative check battery.
- `.claude/settings.json` and other agent host configuration: managed base
  settings only; installed integrations layer tool-owned hook groups onto the
  live files.
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

## Verification

Run the smallest relevant checks; `make verify` is the authoritative
repository-wide battery (syntax, tmux, temp-home install, bootstrap budget,
index parity, tracked-path hygiene). It does not yet cover the isolated
profile checks — run those separately when profiles change:

```sh
sh -n tests/install.sh
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
