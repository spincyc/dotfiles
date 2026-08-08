# ML4W hyprlang-to-Lua migration (opened 2026-08-08)

Hyprland removes the `.conf` (hyprlang) configuration format in 0.57. This
document records the confirmed evidence, the version state at the time of
writing, and the staged plan. It is the durable record for the migration; it
should be deleted once the legacy profile layer is gone.

## Confirmed evidence

The removal is not a forecast. The Hyprland 0.56.2 binary installed on this
host carries the notice as a compiled string:

```console
$ strings /usr/bin/Hyprland | grep 'config format'
You are using the .conf config format, support for which will be removed in Hyprland 0.57.
```

Supporting upstream statements:

- Hyprland deprecated hyprlang in favour of Lua in 0.55.0 (2026-05-09) and
  stated the old syntax would survive "1 - 2 releases starting from 0.55".
  See <https://hypr.land/news/26_lua/>.
- 0.56.1 (2026-07-27) added the deprecation notice quoted above.
- The Lua entry point is `$XDG_CONFIG_HOME/hypr/hyprland.lua`. See
  <https://wiki.hypr.land/Configuring/Start/>.

ML4W has already completed its side of the migration:

- ML4W 2.13.0 (2026-05-31) converted the whole Hyprland configuration to Lua
  and shipped `~/.config/ml4w/scripts/ml4w-remove-conf` to delete the replaced
  `.conf` files. Tracked as
  <https://github.com/mylinuxforwork/dotfiles/issues/1580>.
- ML4W 2.14.0 (2026-06-28) and 2.15 (2026-08-05) followed on that baseline.

## Version state at 2026-08-08

| Component | Version | Format |
| --- | --- | --- |
| Hyprland, released | 0.56.2 (2026-08-05) | hyprlang still accepted |
| Hyprland, this host | 0.56.2 | hyprlang, warning at every start |
| ML4W, released | 2.15 (2026-08-05) | Lua |
| ML4W, this host | 2.12.0 marker, `2.9.9.5` version name | hyprlang |
| This repository | `profiles/ml4w/legacy-2.9.9.5/` | hyprlang |

Hyprland minor releases have been landing about ten weeks apart (0.55.0 on
2026-05-09, 0.56.0 on 2026-07-20), which puts 0.57 near the end of
2026 Q3. That is an estimate from cadence, not an upstream commitment.

## Decision

Migrate now rather than waiting for 0.57, and stay on mainline Hyprland and
mainline ML4W. No local fork of either.

The migration is not blocked on Hyprland. Lua has been accepted since 0.55.0
and this host already runs 0.56.2, so the Lua payload is deployable today. The
real prerequisite is upgrading the live ML4W installation from 2.12.0 to 2.15
through ML4W's own installer.

Waiting until 0.57 arrives would force an ML4W feature upgrade and a config
format migration at the same time, on a compositor that no longer starts the
old configuration. That is the failure mode this plan avoids.

## Scope

The forcing function is Hyprland, but the unit of change is the whole profile
layer. `legacy-2.9.9.5/` is pinned to an ML4W baseline three feature releases
old, and `PROVENANCE.md` there already records that the captured tree mixed
`2.9.9.5` installer metadata with later rolling files. Re-pinning to 2.15
re-baselines all fifteen manifest entries, not only the five Hyprland ones.

Hyprland payload mapping, from the ML4W 2.15 tree
(<https://github.com/mylinuxforwork/dotfiles/tree/main/dotfiles/.config/hypr>):

| `legacy-2.9.9.5` path | 2.15 path | Change |
| --- | --- | --- |
| `conf/custom.conf` | `custom.lua` | Moves out of `conf/`; loaded by a conditional `require("custom")` |
| `conf/keybinding.conf` | `conf/keybinding.lua` | `source =` becomes `load_variant(name,"keybindings")` |
| `conf/monitor.conf` | `conf/monitor.lua` | `source =` becomes `load_variant(name,"monitors")` |
| `conf/monitors/ultrawide-desktop.conf` | `.lua` | Three `monitor=` lines become `hl.monitor({...})` calls |
| `conf/keybindings/ultrawide-desktop.conf` | `.lua` | About fifty binds become `hl.bind()` with `hl.dsp.*` dispatchers |

Installer changes:

- `install.sh` pins the ML4W version to `2.9.9.5`; the gate has to accept the
  new profile version as well while the legacy layer still exists.
- `install.sh` proves the live Hyprland schema by grepping `hyprland.conf` for
  `source = ~/.config/hypr/conf/custom.conf`. Under 2.15 the equivalent proof
  is the conditional `require("custom")` block in `hyprland.lua`.

That gate fails closed. When ML4W is upgraded before this repository is ready,
the installer dies with `live Hyprland schema does not load custom.conf` and
deploys nothing, which is the correct outcome rather than a partial overlay.

## Stages

1. **Repository payload.** Add `profiles/ml4w/2.15/` beside the legacy layer
   and translate the five Hyprland files. No change to `~/.config`.
2. **Semantic unknowns.** Resolve the constructs listed below before the
   payload is trusted.
3. **Live upgrade.** Requires a session restart, so it is the user's call.
   Upgrade ML4W to 2.15 with its own installer, re-verify the ten non-Hyprland
   manifest destinations against what 2.15 actually ships, correct drift, then
   deploy the profile. Rollback is the ML4W backup under `~/.mydotfiles/backups`
   plus a checkout of the legacy layer.
4. **After 0.57 ships.** Confirm no deprecation notice remains, then delete
   `legacy-2.9.9.5/` and collapse the installer version gate back to a single
   pinned version.

## Open questions

Constructs in the legacy keybinding payload with no mechanically obvious Lua
equivalent. Each is resolved in stage 2 and the outcome recorded here.

- `$mainMod = SHIFT CTRL`: how a multi-modifier main modifier is spelled.
- `monitor=DP-3,5120x1440@239.76Hz,auto,1`: whether `hl.monitor` accepts a
  refresh rate inside `mode`. Upstream examples omit one.
- `workspace, e+1` and `e-1` bound to `mouse_down` and `mouse_up`.
- `workspace, empty`.
- `bind = , code:238` and `code:237`: raw keycodes for the keyboard backlight.
- `$SCRIPTS/wlogout.sh` and `$SCRIPTS/cliphist.sh`: 2.15 renamed several ML4W
  scripts, so these exec paths need re-verification.
- The Quickshell IPC invocation behind `$ML4WSETTINGS`.
- `custom.conf` sets `input` scalars including `sensitivity` and
  `mouse_refocus`. In 2.15 input configuration lives in a top-level
  `input.lua`, so the override target may have moved.
