-------------------------------------------------------
-- Named monitor variation for a built-in panel and ultrawide DisplayPort panel.
-- name: "ultrawide-desktop"
-------------------------------------------------------

local BUILT_IN = "eDP-1"

-- The ultrawide is matched on its description because its DisplayPort
-- connector re-enumerates across sessions -- DP-3 became DP-1 on 2026-08-31 --
-- which silently retires a rule pinned to the connector name and drops the
-- display onto the fallback rule below.
local ULTRAWIDE = "desc:Samsung Electric Company Odyssey G95C"

-- Both positions are pinned rather than left to "auto" so the arrangement can
-- neither depend on the order the rules are applied in nor put the panel on
-- the ultrawide's origin. 5120 is the ultrawide's own width.
local ULTRAWIDE_POSITION = "0x0"
local BUILT_IN_POSITION = "5120x0"

hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = 1,
})

hl.monitor({
    output = ULTRAWIDE,
    mode = "5120x1440@239.76",
    position = ULTRAWIDE_POSITION,
    scale = 1,
})

hl.monitor({
    output = BUILT_IN,
    mode = "preferred",
    position = BUILT_IN_POSITION,
    scale = 1,
})

-------------------------------------------------------
-- Clamshell handling
--
-- With the lid shut Hyprland stops driving the built-in panel but leaves
-- eDP-1 *enabled* at a 0x0 mode positioned at 0,0 -- exactly on top of the
-- ultrawide's origin. Clients then see a zero-size wl_output covering the
-- corner. Firefox constrains its menu popups to that empty rectangle, so
-- dropdowns stop rendering entirely; disabling the output restores them.
-- 2026-08-12: verified on Hyprland 0.56.2 with Firefox 153.0.4.
--
-- Hyprland reaches the same state when it starts with the lid already shut,
-- so the state is reconciled on startup and on monitor hotplug, not only on
-- the lid transition. The built-in panel is never disabled while it is the
-- only monitor left: removing the last output puts Hyprland in its unsafe
-- state, which is a worse failure than the one being fixed.
--
-- 2026-08-31: no reconcile runs until Xwayland has settled. Disabling an
-- output destroys its wl_output global, and destroying one while Xwayland
-- binds the registry kills Xwayland: "wl_registry error 0: global wl_output
-- (73) is unavailable". Hyprland never respawns it, yet keeps
-- /tmp/.X11-unix/X0 listening and unserved, so every X11 client afterwards
-- blocks forever in connect() -- Remmina hung with no window at all, because
-- FreeRDP calls XOpenDisplay() while Remmina loads its plugins. Only the bind
-- window is dangerous: a running Xwayland handles output removal normally, and
-- one that starts later never sees the panel.
--
-- Parking the panel beside the layout instead of disabling it keeps the output
-- alive, and was rejected the same day: an enabled output behind a shut lid
-- claims a workspace, so windows open on a screen that cannot be seen.
-------------------------------------------------------

-- Two consecutive sightings put Xwayland's registry bind safely in the past.
-- The ceiling covers a session where no X client ever triggers Hyprland's lazy
-- Xwayland start, and costs only a few seconds of the state being unreconciled.
local XWAYLAND_POLL_MS = 500
local XWAYLAND_GRACE_MS = 15000

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
local xwayland_settled = false

local function reconcile()
    if reconciling or not xwayland_settled then
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
                position = BUILT_IN_POSITION,
                scale = 1,
            })
        else
            hl.monitor({ output = BUILT_IN, disabled = true })
        end
    end

    -- The HiFi__HDMI1/2/3 sink names track ALSA PCM indices, which rebind to
    -- connectors on hotplug, so the stored default sink can silently point at
    -- a dead pin; repin it to the display sink with a valid ELD instead.
    os.execute("setsid -f ~/.config/hypr/scripts/default_sink_by_eld.sh >/dev/null 2>&1")

    reconciling = false
end

local function xwayland_is_running()
    local probe = io.popen("pgrep -x Xwayland >/dev/null 2>&1 && echo running")
    if not probe then
        return false
    end
    local answer = probe:read("*a") or ""
    probe:close()
    return answer:match("running") ~= nil
end

local gate = nil

-- Holds the startup pass, and the eDP-1 monitor.added that races it, away from
-- Xwayland's registry bind. Reconciling stays immediate once the gate opens.
local function await_xwayland()
    if xwayland_settled then
        return
    end
    if gate then
        gate:set_enabled(false)
    end

    local waited, seen_running = 0, false
    local this
    this = hl.timer(function()
        waited = waited + XWAYLAND_POLL_MS
        local running = xwayland_is_running()
        if (running and seen_running) or waited >= XWAYLAND_GRACE_MS then
            this:set_enabled(false)
            xwayland_settled = true
            reconcile()
        else
            seen_running = running
        end
    end, { timeout = XWAYLAND_POLL_MS, type = "repeat" })
    gate = this
end

-- Arming at load time covers a config reload, which re-executes this file
-- without re-firing hyprland.start. Arming again on start covers the reverse
-- risk, that timers are not serviced yet while the config is still executing.
await_xwayland()
hl.on("hyprland.start", await_xwayland)
hl.on("monitor.added", reconcile)
hl.on("monitor.removed", reconcile)

hl.bind("switch:on:Lid Switch", reconcile,
    { locked = true, description = "Disable the built-in panel when the lid closes" })
hl.bind("switch:off:Lid Switch", reconcile,
    { locked = true, description = "Restore the built-in panel when the lid opens" })
