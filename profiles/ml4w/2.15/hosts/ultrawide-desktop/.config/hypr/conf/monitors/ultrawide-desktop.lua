-------------------------------------------------------
-- Named monitor variation for a built-in panel and ultrawide DisplayPort panel.
-- name: "ultrawide-desktop"
-------------------------------------------------------

hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = 1,
})

hl.monitor({
    output = "eDP-1",
    mode = "preferred",
    position = "auto",
    scale = 1,
})

hl.monitor({
    output = "DP-3",
    mode = "5120x1440@239.76",
    position = "auto",
    scale = 1,
})

-------------------------------------------------------
-- Clamshell handling
--
-- With the lid shut Hyprland stops driving the built-in panel but leaves
-- eDP-1 *enabled* at a 0x0 mode positioned at 0,0 -- exactly on top of DP-3's
-- origin. Clients then see a zero-size wl_output covering the ultrawide's
-- corner. Firefox constrains its menu popups to that empty rectangle, so
-- dropdowns stop rendering entirely.
-- 2026-08-12: verified on Hyprland 0.56.2 with Firefox 153.0.4.
--
-- The panel is therefore parked past the right edge of every other output,
-- where a zero-size output overlaps nothing. `position = "auto"` is not
-- enough, because the placement Hyprland picks for the undriven output is
-- 0,0; the explicit position has to be re-applied whenever the lid moves or
-- the other outputs change, which is what the reconcile below is for.
--
-- 2026-08-31: parking replaced disabling the output, which fixed the popups
-- but broke X11 outright. Disabling destroys the panel's wl_output global,
-- and the startup reconcile did that while Xwayland was binding the registry:
-- Xwayland died with "wl_registry error 0: global wl_output (73) is
-- unavailable". Hyprland never respawns it, yet keeps /tmp/.X11-unix/X0
-- listening and unserved, so every later X11 client blocked forever in
-- connect(). Remmina hung with no window at all, because FreeRDP calls
-- XOpenDisplay() while Remmina loads its plugins, before any UI exists.
-- Keeping the output alive avoids that class of failure entirely.
-------------------------------------------------------

local BUILT_IN = "eDP-1"

-- hl.get_monitors() reports enabled monitors only, so a disabled built-in
-- panel is absent rather than flagged.
local function survey()
    local built_in, right_edge = nil, 0
    local monitors = hl.get_monitors() or {}
    for i = 1, #monitors do
        local monitor = monitors[i]
        if monitor.name == BUILT_IN then
            built_in = monitor
        else
            -- Layout coordinates are logical pixels, monitor.width is physical.
            local scale = monitor.scale or 1
            local edge = monitor.x + math.floor(monitor.width / scale + 0.5)
            if edge > right_edge then
                right_edge = edge
            end
        end
    end
    return built_in, right_edge
end

local reconciling = false

local function reconcile()
    if reconciling then
        return
    end
    reconciling = true

    local built_in, right_edge = survey()

    -- `disabled = false` states the intent rather than repairing anything: a
    -- panel that an earlier revision of this file disabled returns at the next
    -- Hyprland start, once no rule disables it.
    if not built_in or built_in.x ~= right_edge or built_in.y ~= 0 then
        hl.monitor({
            output = BUILT_IN,
            mode = "preferred",
            position = string.format("%dx0", right_edge),
            scale = 1,
            disabled = false,
        })
    end

    reconciling = false
end

hl.on("hyprland.start", reconcile)
hl.on("monitor.added", reconcile)
hl.on("monitor.removed", reconcile)

hl.bind("switch:on:Lid Switch", reconcile,
    { locked = true, description = "Park the built-in panel when the lid closes" })
hl.bind("switch:off:Lid Switch", reconcile,
    { locked = true, description = "Reposition the built-in panel when the lid opens" })
