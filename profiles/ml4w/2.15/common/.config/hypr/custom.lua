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
