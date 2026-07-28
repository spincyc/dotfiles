# ML4W legacy profile provenance

This directory contains a curated, modified ML4W configuration profile. It is
not a pristine copy of any single upstream release or commit.

## Upstream identity

- Project: ML4W Dotfiles for Hyprland
- Upstream repository: <https://github.com/mylinuxforwork/dotfiles>
- Active installer profile ID observed on the source system:
  `com.ml4w.dotfiles`
- Legacy installer name/version observed on the source system:
  `ML4W Dotfiles for Hyprland (ROLLING RELEASE)` / `2.9.9.5`
- Upstream tag: `2.9.9.5`
- Upstream tag commit:
  `2236fd9a1db0cb5cb83722e3b63155c30159b363`
- Nearest upstream rolling baseline observed before the source system's
  2026-04-18 profile updates:
  `236948aa317e12a1617764cdf83471dc32c33416` (2026-04-15)
- Active `.config/ml4w/version/name` marker used by the compatibility gate:
  `2.9.9.5`
- A live `.config/ml4w/version.json` marker reported `2.12.0`.

The upstream `LICENSE` at tag `2.9.9.5` is Git blob
`30ace6a87310f143f38bc99a5b22a0f6ae231718`.

## Why the baseline is mixed

The source profile retained its `2.9.9.5` installer metadata while later
rolling files were copied into the same profile directory. Some restored
configuration files remained byte-identical to the `2.9.9.5` tag, other files
matched or followed the 2026-04-15 rolling baseline, and the source system then
added local preferences and generated runtime state. Repeated profile restores
also produced nested duplicate directories.

Accordingly, neither the `2.9.9.5` label nor the `2.12.0` marker describes the
captured source tree by itself. This repository profile preserves only reviewed
semantic configuration, split into:

- `common/`: portable preferences shared by machines using this profile.
- `hosts/ultrawide-desktop/`: configuration for the semantic
  `ultrawide-desktop` machine class. This public name is not a hostname.

Generated color files, editor backups, recursive restore artifacts, stale
vendor files, credentials, and private host identity are intentionally
excluded. The exact deployable file set and destination of every file are
recorded in `manifest`. Small ML4W UI-written selectors for the dock, launcher,
Rofi border, Walker theme, Waybar theme, and SwayNC theme are intentionally
tracked as declarative preferences; their generated color and runtime outputs
are not.

## Modification notice

The payload in `common/` and `hosts/` was selected and modified from the
observed ML4W configuration on 2026-07-28. See `LICENSES/README.md` for the
license boundary and `LICENSES/GPL-3.0.txt` for the applicable license text.
