-- Mesen 2 GBA: 인트로를 건너뛰고 초기 메뉴/텍스트 화면을 순회한다.
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local idx = 1

local function pulse(button, first, last)
  return frame >= first and frame <= last, button
end

emu.addEventCallback(function()
  local buttons = {}
  local active, button
  for _, item in ipairs({
    {"start", 120, 127}, {"start", 300, 307},
    {"a", 520, 527}, {"a", 760, 767},
    {"a", 1000, 1007}, {"start", 1240, 1247},
    {"a", 1500, 1507}, {"a", 1760, 1767},
    {"a", 2050, 2057}, {"a", 2350, 2357},
  }) do
    active, button = pulse(item[1], item[2], item[3])
    if active then buttons[button] = true end
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function save(name)
  local png = emu.takeScreenshot()
  local path = OUT_DIR .. "/" .. name .. ".png"
  local f = io.open(path, "wb")
  if f then f:write(png); f:close(); emu.log("saved " .. path) end
end

emu.addEventCallback(function()
  frame = frame + 1
  while idx <= #SHOTS and SHOTS[idx].frame <= frame do
    save(string.format("%05d_%s", SHOTS[idx].frame, SHOTS[idx].name))
    idx = idx + 1
  end
  if idx > #SHOTS then emu.stop(0) end
end, emu.eventType.endFrame)
