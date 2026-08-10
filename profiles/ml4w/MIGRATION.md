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

| Stage | Outcome | State |
| --- | --- | --- |
| 1 | `profiles/ml4w/2.15/` exists beside the legacy layer, five Hyprland files translated, installer selects a layer from the live release | Done 2026-08-08 |
| 2 | Every hyprlang construct has a Lua equivalent, inferences flagged | Done 2026-08-08 |
| 3 | Live ML4W upgraded to 2.15 and the Lua profile deployed | Done 2026-08-10 |
| 4 | Legacy layer and this document deleted after 0.57 ships | Pending |

Stage 1 also found that the migration is narrower than first scoped. Every ML4W
extension point behind the ten non-Hyprland manifest entries still exists at tag
2.15, so those files carried across unchanged and only the five Hyprland files
were translated. Waybar survives in 2.15; Quickshell is additive rather than a
replacement.

### Two facts learned during the live upgrade (2026-08-10)

**No version marker on disk identifies the installed ML4W release.** The
installer (0.2.5) writes `config.dotinst` and `.config/ml4w/version/name` once
at first install and never rewrites them on upgrade; upstream ships
`.config/ml4w/version.json` stale. After upgrading this host to the 2.15
payload, all three still reported pre-2.15 versions. Layer selection therefore
reads the deployed loader, not a version string. This was caught only because
`--check` selected the hyprlang layer against a Lua tree and would have
deployed dead config.

**Hyprland resolves the config format once, at startup.** `hyprland.lua` wins
over `hyprland.conf` when both exist, but the check does not run again on
`hyprctl reload`. A session started from `hyprland.conf` keeps reading
`hyprland.conf` no matter how many times it is reloaded, and if that file is
removed mid-session Hyprland falls back to its built-in autogenerated config
rather than picking up the Lua one. Two consequences:

- `hyprctl reload` cannot smoke-test a hyprlang-to-Lua migration. Only a
  restart proves it.
- Leaving the stale `hyprland.conf` in place is the cheapest rollback. It is
  inert while `hyprland.lua` exists, so renaming `hyprland.lua` and restarting
  restores the known-good hyprlang session. Run `ml4w-remove-conf` only after
  the Lua session is confirmed good.

### Stage 3 runbook

Each step is safe to stop after. Rollback at any point is the ML4W backup under
`~/.mydotfiles/backups` plus the legacy layer, which stays functional and is
re-selected automatically the moment `config.dotinst` reads `2.9.9.5` again.

| # | Step | Command | Expected | State |
| --- | --- | --- | --- | --- |
| 1 | Upgrade ML4W, pinned to the tag | `ml4w-dotfiles-installer --install https://raw.githubusercontent.com/mylinuxforwork/dotfiles/2.15/hyprland-dotfiles.dotinst` | Backs up to `~/.mydotfiles/backups`. Accept the pre-selected restore list: it preserves user state this repository does not track. Do not pass `--target`; the help text's default is wrong | Done |
| 2 | Restore the core links | `./install.sh` | ML4W's symlink deployment reclaims `~/.zshrc` for its own tree on every upgrade. This takes it back | Done |
| 3 | Dry run | `./install.sh --check --profile ml4w --host-profile ultrawide-desktop` | Reports the Lua destinations as missing or drifted. If it names `conf/custom.conf`, layer selection is wrong — stop | Done |
| 4 | Deploy | `./install.sh --profile ml4w --host-profile ultrawide-desktop` | A following `--check` exits clean | Done |
| 5 | Restart the session | reboot, or log out and back in | The only way to move Hyprland from hyprlang to Lua. See the startup-resolution note above | Done |
| 6 | Exercise the bindings | — | Work through the table below | Done |
| 7 | Clean up ML4W's orphans | `~/.config/ml4w/scripts/ml4w-remove-conf` | Deletes `hyprland.conf` and the replaced `.conf` files. Do this only once step 6 passes: until then that file is the rollback | Pending |

If the Lua session fails to start cleanly, Hyprland loads its built-in config
and shows the "autogenerated config" nag. That is recoverable, not a lockout —
the default binds give `SUPER + Q` for a terminal. From there, rename
`~/.config/hypr/hyprland.lua` and restart to land back on the hyprlang session.

### Post-deploy checks

Syntax is proven; runtime behaviour is not. Ranked by how likely each is to be
wrong.

Confirmed working after the 2026-08-10 restart: all 58 binds registered with
their descriptions, `hyprctl configerrors` is empty, `DP-3` runs at
`5120x1440@239.761`, and every `custom.lua` scalar applied including
`mouse_refocus`, `sensitivity`, and `preserve_split`.

The Lua parser also surfaced a binding that had been dead for as long as it has
existed. `XF86Lock` is not a keysym: it is absent from
`xkbcommon-keysyms.h` and from X11's `XF86keysym.h`, and `xkbcli` rejects it.
hyprlang accepted the string silently, so `bind = , XF86Lock, exec, hyprlock`
never fired. It is removed rather than guessed at; identify the real key with
`wev` before rebinding. Treat this as the general lesson: strings hyprlang
accepted are not evidence that the binding worked.

| Risk | Binding or setting | Notes |
| --- | --- | --- |
| Low | `SHIFT+CTRL+N`, empty workspace | `hyprctl dispatch workspace empty` returns `ok` but does not move focus on this two-monitor layout, and that is already true under hyprlang. The bind is inert either way, so the translation changes nothing |
| High | `SHIFT+CTRL` + scroll, workspace `e+1` and `e-1` | Selector-string passthrough, same fix shape as `empty` |
| High | `SHIFT+CTRL+ALT+I/J/K/L`, resize | `relative = true` semantics unconfirmed |
| Medium | Keyboard backlight `code:238` and `code:237` | The `code:` prefix is confirmed; the `tpacpi::kbd_backlight` device is the likelier failure |
| Medium | `SHIFT+CTRL+Q` and `SHIFT+CTRL+V` | Renamed to `ml4w-power` and `ml4w-cliphist`; confirm both exist |
| Medium | `SHIFT+CTRL+E`, file manager | Lost its `.sh` suffix in 2.15 |
| Low | `DP-3` at `5120x1440@239.76` | Evidenced by ML4W's own `2560x1440@120.lua` |
| Low | XF86 media and brightness keys | Direct upstream pattern match |

### Stage 4

| Trigger | Step | Expected |
| --- | --- | --- |
| 0.57 reaches Arch | `pacman -Syu`, then watch startup | No deprecation notice means the migration held |
| Confirmed clean | Delete `profiles/ml4w/legacy-2.9.9.5/` | Payload, `PROVENANCE.md` and `LICENSES/` go with it |
| Same commit | Reduce `ml4w_profile_dir_for_version` to one entry and drop the `legacy-2.9.9.5` branches in the loader gate | `install.sh` ends up simpler than before the migration |
| Same commit | Delete this document | It is a migration record, not permanent documentation |

If ML4W ships 2.16 or later before 0.57 arrives, re-pin instead: add the version
to the table in `install.sh`, copy `profiles/ml4w/2.15/` to the new version, and
re-verify the extension points. That is much cheaper than this round, because
the hyprlang translation is a one-time cost.

## Resolved constructs (stage 2, 2026-08-08)

Every construct in the legacy keybinding payload now has a Lua equivalent.
Unless noted, the evidence is ML4W 2.15's own
`.config/hypr/conf/keybindings/default.lua`.

| Legacy | Lua |
| --- | --- |
| `$mainMod = SHIFT CTRL` | `local mainMod = "SHIFT + CTRL"`, composed with `..` |
| `monitor=...,5120x1440@239.76Hz,...` | `mode = "5120x1440@239.76"`; the refresh rate goes inside `mode` with no `Hz` suffix, as in ML4W's `2560x1440@120.lua` |
| `bind = $mainMod, mouse_down, workspace, e+1` | `hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))` |
| `bindm = ALT, mouse:272, movewindow` | `hl.bind("ALT + mouse:272", hl.dsp.window.drag(), { mouse = true })` |
| `bind = , XF86AudioMute, exec, ...` | `hl.bind("XF86AudioMute", hl.dsp.exec_cmd(...), { locked = true })` |
| `bind = , code:238, exec, ...` | `hl.bind("code:238", hl.dsp.exec_cmd(...))`; the `code:` prefix survives |
| `killactive` | `hl.dsp.window.close()` |
| `togglefloating` | `hl.dsp.window.float({ action = "toggle" })` |
| `fullscreen` | `hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle" })` |
| `movefocus, l` | `hl.dsp.focus({ direction = "left" })` |
| `resizeactive, 100 0` | `hl.dsp.window.resize({ x = 100, y = 0, relative = true })` |
| `workspace, 3` | `hl.dsp.focus({ workspace = 3 })` |

ML4W 2.15 script renames that the host keybinding payload has to follow:

| Legacy | 2.15 |
| --- | --- |
| `~/.config/ml4w/scripts/wlogout.sh` | `~/.config/ml4w/scripts/ml4w-power` |
| `~/.config/ml4w/scripts/cliphist.sh` | `~/.config/ml4w/scripts/ml4w-cliphist` |
| `~/.config/ml4w/settings/filemanager.sh` | `~/.config/ml4w/settings/filemanager` |

`~/.config/hypr/scripts/{moveTo,screenshot,loadconfig,toggle-animations}.sh`,
`~/.config/waybar/launch.sh`, `~/.config/ml4w/settings/{terminal,browser,calculator}.sh`,
`waypaper`, `rofi`, and `hyprlock` are unchanged in 2.15.

`$ML4WSETTINGS` also stays as it is. The ML4W Settings app is a separate
upstream project (`mylinuxforwork/dotfiles-settings`) installed under
`~/.local/share/ml4w-dotfiles-settings/`, so its Quickshell IPC invocation does
not move with a dotfiles release.

The `input` overrides stay in `custom.lua`. 2.15 does read input configuration
from a top-level `input.lua`, but `hyprland.lua` runs `require("custom")` after
every `conf.*` and after `require("input")`, so a later `hl.config({ input = ... })`
still wins.

### Inference, not yet proven

`bind = $mainMod, N, workspace, empty` is translated as
`hl.dsp.focus({ workspace = "empty" })`. No upstream Lua example uses `empty`,
and the third-party Lua API reference does not list it — but that reference
also omits `e+1`, which ML4W demonstrably uses, so it is incomplete rather than
authoritative. The reading is that the Lua layer passes the workspace selector
string through to the same parser hyprlang used. Prove it at stage 3 with:

```sh
hyprctl dispatch workspace empty
```

## Version markers, settled 2026-08-10

`version` and `version_name` in `profiles/ml4w/2.15/profile.conf` are
declarative provenance recording the upstream release the layer was derived
from. They are no longer compared against the live tree, and the gate reads no
version marker at all:

| Marker | Rewritten on upgrade? | Reported after upgrading to the 2.15 payload |
| --- | --- | --- |
| `config.dotinst` `.version` | No, first-install artifact | `2.9.9.5` |
| `.config/ml4w/version/name` | No | `2.9.9.5` |
| `.config/ml4w/version.json` `.Version` | Yes, but upstream ships it stale | `2.12.3` |

`config.dotinst` remains authoritative for the profile ID, upstream source, and
subfolder. Only its version field rots.
