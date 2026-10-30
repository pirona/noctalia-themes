--!nonstrict
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Now playing card: follows the MPRIS player picked by playerctl, inside the theme's sliced frame.

local SEP = "\t"
local FORMAT = table.concat({
  "{{playerInstance}}", "{{status}}", "{{artist}}", "{{title}}", "{{mpris:artUrl}}",
}, SEP)
local CACHE = noctalia.pluginDataDir() .. "/covers"
noctalia.mkdirAll(CACHE)
for _, name in noctalia.listDir(CACHE) or {} do -- one cover on disk at a time: drop leftovers
  noctalia.removeFile(CACHE .. "/" .. name)
end

local fillColor = noctalia.getConfig("fill")
local textColor = noctalia.getConfig("color")
local fontFamily = noctalia.getConfig("font_family")
if fontFamily == "" then fontFamily = nil end
local hideWhenIdle = noctalia.getConfig("hide_when_idle")

-- Frame: four bands laid around the content (plugin UIs cannot stack an image under it).
local frame = nil
do
  local dir = noctalia.expandPath(noctalia.getConfig("frame") or "")
  local raw = dir ~= "" and noctalia.readFile(dir .. "/frame.json")
  if raw then
    local m = noctalia.json.decode(raw)
    local s = m.scale
    frame = {
      dir = dir, bands = m.bands,
      w = m.width / s, h = m.height / s,
      l = m.inset[1] / s, t = m.inset[2] / s, r = m.inset[3] / s, b = m.inset[4] / s,
    }
    frame.innerW = frame.w - frame.l - frame.r
    frame.innerH = frame.h - frame.t - frame.b
    if m.fill then fillColor = m.fill end
  end
end

local track = { player = "", status = "", artist = "", title = "", art = "" }
local noPlayerctl = not noctalia.commandExists("playerctl") -- say so instead of "nothing playing" forever
local cover = nil -- cached cover path, nil while none

local function control(action)
  if track.player ~= "" then noctalia.runAsync({ "playerctl", "-p", track.player, action }) end
end
function onPrevious() control("previous") end
function onPlayPause() control("play-pause") end
function onNext() control("next") end

local function content(w, h)
  local pad = 8
  local side = h - 2 * pad
  local img = cover and ui.image({ path = cover, width = side, height = side, fit = "cover" })
    or ui.box({ fill = "surface_variant", width = side, height = side })
  local label = function(text, size, weight)
    return ui.label({ text = text, fontSize = size, fontWeight = weight, fontFamily = fontFamily,
      color = textColor, maxLines = 1 })
  end
  local playing = track.status == "Playing"
  local btn = function(glyph, cb)
    return ui.button({ glyph = glyph, variant = "ghost", controlSize = "sm", onClick = cb })
  end
  return ui.row({ gap = 10, padding = pad, fill = fillColor, width = w, height = h, align = "center" }, {
    img,
    ui.column({ gap = 2, flexGrow = 1 }, {
      label(noPlayerctl and noctalia.tr("ui.no_playerctl")
        or track.title ~= "" and track.title or noctalia.tr("ui.nothing"), 14, "bold"),
      label(track.artist, 12),
      ui.row({ gap = 2 }, {
        btn("player-skip-back", "onPrevious"),
        btn(playing and "player-pause" or "player-play", "onPlayPause"),
        btn("player-skip-forward", "onNext"),
      }),
    }),
  })
end

local function render()
  if hideWhenIdle and not noPlayerctl and (track.title == "" or track.status == "Stopped") then
    desktopWidget.render(ui.column({}, {}))
    return
  end
  if not frame then
    desktopWidget.render(content(320, 112))
    return
  end
  local f = frame
  local band = function(name, w, h) return ui.image({ path = f.dir .. "/" .. f.bands[name], width = w, height = h }) end
  desktopWidget.render(ui.column({ gap = 0 }, {
    band("top", f.w, f.t),
    ui.row({ gap = 0 }, {
      band("left", f.l, f.innerH),
      content(f.innerW, f.innerH),
      band("right", f.r, f.innerH),
    }),
    band("bottom", f.w, f.b),
  }))
end

-- Cached copy named after the track: the image loader caches by path.
local function cacheName(s)
  local h = 5381
  for i = 1, #s do h = (h * 33 + string.byte(s, i)) % 4294967296 end
  return string.format("%s/%08x", CACHE, h)
end

local wanted = nil -- cache path of the current track's cover

local function setCover(path, forDest)
  if forDest ~= wanted then return end -- a newer track took over while this one was fetched
  if cover and cover ~= path then noctalia.removeFile(cover) end
  cover = path
  render()
end

-- Sandboxed players (Flatpak, Chromium) write art into a private /tmp: read it through their own root.
local function copyLocal(src, dest)
  noctalia.runAsync({ "busctl", "--user", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
    "org.freedesktop.DBus", "GetConnectionUnixProcessID", "s", "org.mpris.MediaPlayer2." .. track.player },
    function(r)
      local pid = string.match(r.stdout or "", "u (%d+)")
      local candidates = { src }
      if pid then table.insert(candidates, "/proc/" .. pid .. "/root" .. src) end
      for _, p in candidates do
        if noctalia.fileExists(p) then
          noctalia.runAsync({ "cp", "-f", p, dest }, function(c) setCover(c.exitCode == 0 and dest or nil, dest) end)
          return
        end
      end
      setCover(nil, dest)
    end)
end

local function resolveCover()
  local url = track.art
  wanted = url ~= "" and cacheName(url .. track.title .. track.artist) or nil
  local dest = wanted
  if not dest then return setCover(nil, nil) end
  if noctalia.fileExists(dest) then return setCover(dest, dest) end
  local localPath = string.match(url, "^file://(.+)$")
  if localPath then
    copyLocal(noctalia.string.urlDecode(localPath), dest)
  elseif string.match(url, "^https?://") then
    noctalia.download(url, dest, function(ok) setCover(ok and dest or nil, dest) end)
  else
    setCover(nil, dest)
  end
end

-- playerctl prints an empty line when the last player goes away.
local function onLine(line)
  local f = line == "" and {} or string.split(line, SEP)
  local prevArt, prevTitle = track.art, track.title
  track.player, track.status, track.artist, track.title, track.art =
    f[1] or "", f[2] or "", f[3] or "", f[4] or "", f[5] or ""
  if track.art ~= prevArt or track.title ~= prevTitle then resolveCover() else render() end
end

if not noPlayerctl then
  noPlayerctl = not noctalia.runStream("playerctl --follow metadata --format '" .. FORMAT .. "'", onLine)
end
render()
