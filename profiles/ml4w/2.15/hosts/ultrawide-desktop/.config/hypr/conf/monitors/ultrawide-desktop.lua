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
-- dropdowns stop rendering entirely; disabling the output restores them.
-- 2026-08-12: verified on Hyprland 0.56.2 with Firefox 153.0.4.
--
-- Hyprland reaches the same state when it starts with the lid already shut,
-- so the state is reconciled on startup and on monitor hotplug, not only on
-- the lid transition. The built-in panel is never disabled while it is the
-- only monitor left: removing the last output puts Hyprland in its unsafe
-- state, which is a worse failure than the one being fixed.
-------------------------------------------------------

local BUILT_IN = "eDP-1"

local function lid_is_closed()
    -- Path component varies by firmware (LID, LID0, ...), so glob it.
    local probe = io.popen("cat /proc/acpi/button/lid/*/state 2>/dev/null")
    if not probe then
        return false
    end
    local state = probe:read("*a") or ""
    probe:close()
    return state:match("closed") ~= nil
end

-- hl.get_monitors() reports enabled monitors only, so absence means disabled.
local function survey()
    local built_in_enabled, others = false, 0
    local monitors = hl.get_monitors() or {}
    for i = 1, #monitors do
        if monitors[i].name == BUILT_IN then
            built_in_enabled = true
        else
            others = others + 1
        end
    end
    return built_in_enabled, others
end

local reconciling = false

local function reconcile()
    if reconciling then
        return
    end
    reconciling = true

    local built_in_enabled, others = survey()
    local want_enabled = not (lid_is_closed() and others > 0)

    if want_enabled ~= built_in_enabled then
        if want_enabled then
            hl.monitor({
                output = BUILT_IN,
                mode = "preferred",
                position = "auto",
                scale = 1,
            })
        else
            hl.monitor({ output = BUILT_IN, disabled = true })
        end
    end

    reconciling = false
end

hl.on("hyprland.start", reconcile)
hl.on("monitor.added", reconcile)
hl.on("monitor.removed", reconcile)

hl.bind("switch:on:Lid Switch", reconcile,
    { locked = true, description = "Disable the built-in panel when the lid closes" })
hl.bind("switch:off:Lid Switch", reconcile,
    { locked = true, description = "Restore the built-in panel when the lid opens" })
