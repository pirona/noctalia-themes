--!nonstrict
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Clock: optional date above the time, inside the theme's frame. One widget, so it moves as one piece.

local frame = require("./frame.luau")
local render -- defined below; the style calls it back once the theme font is loaded
local st = frame.style(function() render() end)

-- Same "{:%H:%M}" format as Noctalia's own clock (the app patches it for 12 h / seconds); formatTime wants "%H:%M".
local function strftime(fmt)
  return string.match(fmt or "", "^{:(.*)}$") or fmt or ""
end
local timeFmt = strftime(noctalia.getConfig("format"))
local dateFmt = strftime(noctalia.getConfig("date_format"))
local size = noctalia.getConfig("size")
local dateSize = noctalia.getConfig("date_size")

local shown = nil

function render()
  local time = noctalia.formatTime(timeFmt)
  local date = dateFmt ~= "" and noctalia.formatTime(dateFmt) or nil
  shown = (date or "") .. "|" .. time
  desktopWidget.render(frame.wrap(st, function(w, h)
    local lines = {}
    if date then table.insert(lines, frame.label(st, date, dateSize)) end
    table.insert(lines, frame.label(st, time, size, true))
    return ui.column({ gap = 0, fill = st.frame and st.fill or nil, width = w, height = h,
      align = "center", justify = "center", padding = st.frame and 0 or 8 }, lines)
  end))
end

-- Called on second boundaries; redraw only when the text changes.
function update()
  local date = dateFmt ~= "" and noctalia.formatTime(dateFmt) or ""
  if date .. "|" .. noctalia.formatTime(timeFmt) ~= shown then render() end
end

desktopWidget.setWantsSecondTicks(true)
render()
