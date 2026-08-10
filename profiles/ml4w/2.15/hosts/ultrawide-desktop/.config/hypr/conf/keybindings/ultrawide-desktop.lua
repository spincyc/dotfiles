-- Named physical-key variation for the ultrawide desktop profile.
-- Translated from the hyprlang payload of the legacy 2.9.9.5 layer. The
-- physical chords are deliberately unchanged; only the syntax and the ML4W
-- 2.15 script names differ.

local mainMod = "SHIFT + CTRL"
local HYPRSCRIPTS = "~/.config/hypr/scripts"
local SCRIPTS = "~/.config/ml4w/scripts"
local ML4WSETTINGS =
    "qs -p ~/.local/share/ml4w-dotfiles-settings/quickshell ipc call settings toggle"

-- Applications
hl.bind(mainMod .. " + T", hl.dsp.exec_cmd("~/.config/ml4w/settings/terminal.sh"), { description = "Open the terminal" })
hl.bind(mainMod .. " + F", hl.dsp.exec_cmd("~/.config/ml4w/settings/browser.sh"), { description = "Open the browser" })
hl.bind(mainMod .. " + E", hl.dsp.exec_cmd("~/.config/ml4w/settings/filemanager"), { description = "Open the filemanager" })

-- Windows
hl.bind("ALT + F4", hl.dsp.window.close(), { description = "Kill active window" })
hl.bind(mainMod .. " + F9", hl.dsp.window.float({ action = "toggle" }), { description = "Toggle floating" })
hl.bind(mainMod .. " + F11", hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle" }), { description = "Toggle fullscreen" })
hl.bind(mainMod .. " + J", hl.dsp.focus({ direction = "left" }), { description = "Move focus left" })
hl.bind(mainMod .. " + L", hl.dsp.focus({ direction = "right" }), { description = "Move focus right" })
hl.bind(mainMod .. " + I", hl.dsp.focus({ direction = "up" }), { description = "Move focus up" })
hl.bind(mainMod .. " + K", hl.dsp.focus({ direction = "down" }), { description = "Move focus down" })
hl.bind("ALT + mouse:272", hl.dsp.window.drag(), { mouse = true, description = "Move window with the mouse" })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true, description = "Resize window with the mouse" })
hl.bind(mainMod .. " + ALT + L", hl.dsp.window.resize({ x = 100, y = 0, relative = true }), { repeating = true, description = "Increase window width" })
hl.bind(mainMod .. " + ALT + J", hl.dsp.window.resize({ x = -100, y = 0, relative = true }), { repeating = true, description = "Reduce window width" })
hl.bind(mainMod .. " + ALT + K", hl.dsp.window.resize({ x = 0, y = 100, relative = true }), { repeating = true, description = "Increase window height" })
hl.bind(mainMod .. " + ALT + I", hl.dsp.window.resize({ x = 0, y = -100, relative = true }), { repeating = true, description = "Reduce window height" })

-- Actions
hl.bind(mainMod .. " + SHIFT + A", hl.dsp.exec_cmd(HYPRSCRIPTS .. "/toggle-animations.sh"), { description = "Toggle animations" })
hl.bind(mainMod .. " + PRINT", hl.dsp.exec_cmd(HYPRSCRIPTS .. "/screenshot.sh"), { description = "Take a screenshot" })
hl.bind(mainMod .. " + CTRL + Q", hl.dsp.exec_cmd(SCRIPTS .. "/ml4w-power"), { description = "Open the power menu" })
hl.bind(mainMod .. " + W", hl.dsp.exec_cmd("waypaper"), { description = "Open the wallpaper selector" })
hl.bind(mainMod .. " + RETURN", hl.dsp.exec_cmd("pkill rofi || rofi -show drun -replace -i"), { description = "Open the application launcher" })
hl.bind(mainMod .. " + SHIFT + B", hl.dsp.exec_cmd("~/.config/waybar/launch.sh"), { description = "Reload the status bar" })
hl.bind(mainMod .. " + ALT + R", hl.dsp.exec_cmd(HYPRSCRIPTS .. "/loadconfig.sh"), { description = "Reload the Hyprland configuration" })
hl.bind(mainMod .. " + V", hl.dsp.exec_cmd(SCRIPTS .. "/ml4w-cliphist"), { description = "Open the clipboard manager" })
hl.bind(mainMod .. " + CTRL + S", hl.dsp.exec_cmd(ML4WSETTINGS), { description = "Open ML4W Settings" })

-- Workspaces
for i = 1, 8 do
    hl.bind(mainMod .. " + " .. i, hl.dsp.focus({ workspace = i }), { description = "Focus workspace " .. i })
    hl.bind("ALT + " .. mainMod .. " + " .. i, hl.dsp.exec_cmd(HYPRSCRIPTS .. "/moveTo.sh " .. i), { description = "Move window to workspace " .. i })
end

hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }), { description = "Switch to next workspace" })
hl.bind(mainMod .. " + mouse_up", hl.dsp.focus({ workspace = "e-1" }), { description = "Switch to previous workspace" })
hl.bind(mainMod .. " + N", hl.dsp.focus({ workspace = "empty" }), { description = "Switch to the first empty workspace" })

-- Function keys
hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd("brightnessctl -q s +10%"), { locked = true, repeating = true, description = "Increase brightness" })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl -q s 10%-"), { locked = true, repeating = true, description = "Decrease brightness" })
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("pactl set-sink-volume @DEFAULT_SINK@ +5%"), { locked = true, repeating = true, description = "Raise volume" })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("pactl set-sink-volume @DEFAULT_SINK@ -5%"), { locked = true, repeating = true, description = "Lower volume" })
hl.bind("XF86AudioMute", hl.dsp.exec_cmd("pactl set-sink-mute @DEFAULT_SINK@ toggle"), { locked = true, description = "Mute audio" })
hl.bind(mainMod .. " + F5", hl.dsp.exec_cmd("quodlibet --play-pause"), { description = "Play or pause" })
hl.bind(mainMod .. " + F6", hl.dsp.exec_cmd("quodlibet --prev"), { description = "Previous track" })
hl.bind(mainMod .. " + F7", hl.dsp.exec_cmd("quodlibet --next"), { description = "Next track" })
hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("playerctl previous"), { locked = true, description = "Previous track" })
hl.bind("XF86AudioMicMute", hl.dsp.exec_cmd("pactl set-source-mute @DEFAULT_SOURCE@ toggle"), { locked = true, description = "Mute microphone" })
hl.bind("XF86Calculator", hl.dsp.exec_cmd("~/.config/ml4w/settings/calculator.sh"), { description = "Open the calculator" })
-- The legacy layer bound hyprlock to XF86Lock. That is not a keysym: it is
-- absent from xkbcommon-keysyms.h and from X11's XF86keysym.h, and xkbcli
-- rejects it, so no key ever emitted it and the bind never fired. hyprlang
-- accepted the string silently; the Lua parser reports it. Identify the real
-- key with `wev` before rebinding it.
hl.bind("XF86Tools", hl.dsp.exec_cmd(ML4WSETTINGS), { description = "Open ML4W Settings" })

hl.bind("code:238", hl.dsp.exec_cmd("brightnessctl -d tpacpi::kbd_backlight s +10"), { locked = true, repeating = true, description = "Increase keyboard backlight" })
hl.bind("code:237", hl.dsp.exec_cmd("brightnessctl -d tpacpi::kbd_backlight s 10-"), { locked = true, repeating = true, description = "Decrease keyboard backlight" })
