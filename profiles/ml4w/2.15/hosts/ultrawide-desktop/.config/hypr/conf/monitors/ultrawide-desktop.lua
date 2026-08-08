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
