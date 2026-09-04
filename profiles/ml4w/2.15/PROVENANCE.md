# ML4W 2.15 profile provenance

This directory contains a curated, modified ML4W configuration profile for the
Lua-based ML4W baseline. It is not a pristine copy of any single upstream
release or commit.

## Upstream identity

- Project: ML4W OS - Dotfiles for Hyprland
- Upstream repository: <https://github.com/mylinuxforwork/dotfiles>
- Installer profile ID: `com.ml4w.dotfiles`
- Installer name/version declared by upstream
  `hyprland-dotfiles.dotinst` at tag `2.15`:
  `ML4W OS - Dotfiles for Hyprland (ROLLING RELEASE)` / `2.15`
- Upstream tag: `2.15`, published 2026-08-05
- Upstream `.config/ml4w/version.json` at that tag reports `2.12.3` and is
  therefore not a usable version source. The compatibility gate reads
  `config.dotinst` and `.config/ml4w/version/name` instead.

## Derivation

Unlike `../legacy-2.9.9.5/`, this layer was not captured from an installed
system. It was derived in two parts on 2026-08-08:

- The eleven `common/` files were carried across unchanged from the
  `legacy-2.9.9.5` layer. They are user-owned override files that sit behind
  ML4W extension points, and every one of those extension points still exists
  at tag `2.15`: `kitty.conf` still runs
  `include $HOME/.config/kitty/custom.conf`, and `waybar/launch.sh` still
  prefers `config-custom` and `style-custom.css` when present.
- The five Hyprland files were translated from hyprlang to Lua against the
  upstream `2.15` payload. Hyprland removes the `.conf` format in 0.57; see
  `../MIGRATION.md` for the evidence, the construct-by-construct mapping, and
  the staged plan.

The `common/` files are duplicated rather than shared with the legacy layer on
purpose. The two layers pin different upstream baselines, so files that are
identical today may legitimately diverge, and the duplication disappears when
the legacy layer is deleted at stage 4 of the migration.

## Translated Hyprland payload

| Destination | Source of the translation |
| --- | --- |
| `.config/hypr/custom.lua` | `legacy-2.9.9.5` `conf/custom.conf`. Moves out of `conf/`; `hyprland.lua` loads it through a conditional `require("custom")` |
| `.config/hypr/conf/keybinding.lua` | `conf/keybinding.conf`, as a `load_variant` call |
| `.config/hypr/conf/monitor.lua` | `conf/monitor.conf`, as a `load_variant` call |
| `.config/hypr/conf/keybindings/ultrawide-desktop.lua` | `conf/keybindings/ultrawide-desktop.conf` |
| `.config/hypr/conf/monitors/ultrawide-desktop.lua` | `conf/monitors/ultrawide-desktop.conf` |

The physical key chords are unchanged from the legacy layer. Three exec targets
changed because ML4W renamed the scripts: `wlogout.sh` to `ml4w-power`,
`cliphist.sh` to `ml4w-cliphist`, and `settings/filemanager.sh` to
`settings/filemanager`.

## Local additions

`.config/hypr/custom.lua` carries locally authored content beyond the file it
was translated from. It registers an `hyprland.start` handler that sets the
wallpaper image with `ml4w-wallpaper --skip-theming` on every login.

That handler works around a defect in upstream `ml4w-autostart`, which skips
the image set whenever awww's cache holds any file at all. awww restores per
output and keys its cache by connector name, so a cache holding only another
output's entry suppresses the set and leaves the desktop at awww's default
black, permanently, because the skipped set is also what would have written an
entry for the live output. The workaround sits behind an ML4W extension point
rather than in a forked copy of `ml4w-autostart`, so no vendor script is
adopted into this profile and an upstream fix cannot be silently overwritten
by one. `--skip-theming` keeps `ml4w-autostart` the sole owner of the theming
pass. See the comment in the file for the full rationale.

## Verification status

The five Lua files parse cleanly under both `luac5.4 -p` and LuaJIT. That
proves syntax only. Their runtime behaviour has not been observed, because this
host still runs the ML4W 2.12.0 rolling tree; see the stage 3 and stage 4
entries in `../MIGRATION.md`.

`version` and `version_name` in `profile.conf` are pinned from upstream
metadata rather than from an observed installation. `version` is well
evidenced. `version_name` is an inference from how the legacy installation
writes the `config.dotinst` version into `.config/ml4w/version/name`, and is
confirmed at stage 3. A wrong value fails the gate closed and deploys nothing.

## Modification notice

The payload in `common/` and `hosts/` was selected and modified from ML4W
configuration on 2026-08-08. See `LICENSES/README.md` for the license boundary
and `LICENSES/GPL-3.0.txt` for the applicable license text. The exact
deployable file set and destination of every file are recorded in `manifest`.

Generated color files, runtime state, credentials, and private host identity
are intentionally excluded. `hosts/ultrawide-desktop/` is a semantic machine
class, not a hostname.
