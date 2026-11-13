--!nonstrict
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Shared by the desktop widgets: style from the widget settings and the theme's frame, cut by
-- tools/slice_frame.py into four bands laid around the content (plugin UIs cannot stack an image under it).

local M = {}

-- WCAG relative luminance and contrast ratio of "#RRGGBB" colours.
local function luminance(hex)
  local function ch(i)
    local c = tonumber(string.sub(hex, i, i + 1), 16) / 255
    return c <= 0.03928 and c / 12.92 or ((c + 0.055) / 1.055) ^ 2.4
  end
  return 0.2126 * ch(2) + 0.7152 * ch(4) + 0.0722 * ch(6)
end

local function contrast(a, b)
  local la, lb = luminance(a), luminance(b)
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05)
end

-- Reads frame / fill / color / font_family. onFont is called once the theme font is loaded.
function M.style(onFont)
  local st = { fill = noctalia.getConfig("fill"), color = noctalia.getConfig("color") }
  local font = noctalia.getConfig("font_family")
  font = font ~= "" and font or nil

  local dir = noctalia.expandPath(noctalia.getConfig("frame") or "")
  local raw = dir ~= "" and noctalia.readFile(dir .. "/frame.json")
  if raw then
    local m = noctalia.json.decode(raw)
    local s = m.scale
    local f = {
      dir = dir, bands = m.bands, o = (m.overlap or 0) / s,
      w = m.width / s, h = m.height / s,
      l = m.inset[1] / s, t = m.inset[2] / s, r = m.inset[3] / s, b = m.inset[4] / s,
    }
    f.innerW = f.w - f.l - f.r
    f.innerH = f.h - f.t - f.b
    st.frame = f
    if m.fill then
      st.fill = m.fill
      -- The drawing fixes the interior colour whatever the light/dark mode: a palette role may vanish on it.
      if string.sub(st.color, 1, 1) ~= "#" then
        local hex = noctalia.getColor(st.color)
        if not hex or contrast(hex, m.fill) < 3 then
          st.color = luminance(m.fill) < 0.18 and "#FFFFFF" or "#000000"
        end
      end
    end
  end

  -- Plugin text only sees fonts it loads itself: find the theme font's file by family name.
  -- st.font only once loaded: an unchanged label keeps its layout, so a family named too early stays in fallback.
  if font then
    noctalia.runAsync({ "fc-match", "-f", "%{family}\t%{file}", font }, function(r)
      local family, file = string.match(r.stdout or "", "^([^\t]*)\t(.+)$")
      if file and string.find(family, font, 1, true) and noctalia.loadFont(file) then
        st.font = font
        onFont()
      end
    end)
  end
  return st
end

-- content(w, h) builds the inner node; w, h are nil without a frame (natural size).
function M.wrap(st, content)
  local f = st.frame
  if not f then return content(nil, nil) end
  local band = function(name, w, h) return ui.image({ path = f.dir .. "/" .. f.bands[name], width = w, height = h }) end
  -- ponytail: negative gap (undocumented, works on 5.4) overlaps bands by f.o so scaling leaves no seam
  return ui.column({ gap = -f.o }, {
    band("top", f.w, f.t + f.o),
    ui.row({ gap = -f.o }, {
      band("left", f.l + f.o, f.innerH),
      content(f.innerW, f.innerH),
      band("right", f.r + f.o, f.innerH),
    }),
    band("bottom", f.w, f.b + f.o),
  })
end

-- Label in the widget's colour and font; no bold with a theme font (hand-lettering fonts often ship one weight).
function M.label(st, text, size, bold)
  return ui.label({ text = text, fontSize = size, fontWeight = (bold and not st.font) and "bold" or nil,
    fontFamily = st.font, color = st.color, maxLines = 1 })
end

return M
