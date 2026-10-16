-- Mesen 2 GBA: reach the title/file-select screens from a clean boot.
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local idx = 1

emu.addEventCallback(function()
  local buttons = {}
  if (frame >= 3520 and frame <= 3527) or (frame >= 3720 and frame <= 3727) then
    buttons["start"] = true
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
