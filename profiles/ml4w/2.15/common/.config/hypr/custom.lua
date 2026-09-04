-- User-owned overrides for the ML4W 2.15 profile.
-- hyprland.lua requires this file last, after every conf.* module and after
-- input.lua, so these values win and any handler registered here runs after
-- the handlers conf/autostart.lua registers.

hl.config({
    general = {
        gaps_in = 1,
        gaps_out = 1,
        border_size = 1,
        layout = "dwindle",
    },

    decoration = {
        rounding = 0,
    },

    dwindle = {
        preserve_split = true,
    },

    input = {
        -- ML4W 2.15's input.lua sets kb_options = "grp:alt_shift_toggle",
        -- which makes xkb claim Alt+Shift as a layout-group switcher. xkb
        -- consumes the combination before Hyprland sees it, so every
        -- SHIFT+CTRL+ALT chord silently degrades to SHIFT+CTRL: the resize
        -- binds land on the focus binds instead. The 2.9.9.5 baseline left
        -- kb_options empty. Only one layout is configured here, so the
        -- toggle has nothing to switch between and is pure breakage.
        kb_options = "",

        numlock_by_default = false,
        follow_mouse = 1,
        mouse_refocus = false,
        sensitivity = -0.5,

        touchpad = {
            natural_scroll = false,
            scroll_factor = 1.0,
            disable_while_typing = false,
        },
    },
})

-------------------------------------------------------
-- Always set the wallpaper image on login
--
-- ML4W's ml4w-autostart skips the image set whenever awww's cache holds any
-- file at all:
--
--     if [[ -z $(find "$AWWW_CACHE_FOLDER" -mindepth 1 -maxdepth 1 -type f ...
--         ml4w-wallpaper "$(cat $CACHE_FILE)" &
--     else
--         ml4w-wallpaper "$(cat $CACHE_FILE)" --skip-wallpaper &
--
-- The guard is meant to avoid a redundant transition, on the assumption that
-- awww restores the cached wallpaper by itself. It does, but per output, and
-- it keys its cache by connector name (~/.cache/awww/<version>/<output>). A
-- cache holding only some other output's entry still satisfies the guard, so
-- the set is skipped, awww finds no entry for the live output, and the desktop
-- stays at awww's default black. Because the set was skipped, nothing ever
-- writes an entry for the live output either, so the state repeats on every
-- login instead of correcting itself.
--
-- 2026-09-04: black desktop on DP-3 with only an eDP-1 entry cached. Theming
-- was unaffected, so the colors, the bar, and the lock screen all looked
-- right while the background alone was blank. This is not a one-off: the
-- ultrawide's DisplayPort connector re-enumerates across sessions, which is
-- why conf/monitors/ultrawide-desktop.lua matches that monitor on its
-- description instead. The awww cache cannot do the same, because the output
-- name is the key.
--
-- Setting the image here keeps the fix behind an ML4W extension point, so no
-- vendor script is forked and an ML4W upgrade cannot quietly revert it.
-- --skip-theming confines this to the image: ml4w-autostart still owns the
-- theming pass, so the two compose into one set and one theme rather than
-- duplicating either. ml4w-wallpaper waits for awww-daemon itself, falls back
-- to the default wallpaper when the cache file is missing, and writes an entry
-- for the live output once it succeeds.
-------------------------------------------------------

hl.on("hyprland.start", function ()
    hl.exec_cmd([[~/.config/ml4w/scripts/ml4w-wallpaper "$(cat ~/.cache/ml4w/hyprland-dotfiles/current_wallpaper 2>/dev/null)" --skip-theming]])
end)
