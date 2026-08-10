-- User-owned scalar overrides for the ML4W 2.15 profile.
-- hyprland.lua requires this file last, after every conf.* module and after
-- input.lua, so these values win.

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
