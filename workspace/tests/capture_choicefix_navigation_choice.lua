-- Clean boot and stop on the initial Navigation objective confirmation.
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local idx = 1

local function held(first, last)
  return frame >= first and frame <= last
end

emu.addEventCallback(function()
  local buttons = {}
  if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
  if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end
  if frame >= 5400 and frame <= 6500 and (frame % 45) <= 5 then buttons["a"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function save(name)
  local png = emu.takeScreenshot()
  local file = io.open(OUT_DIR .. "/" .. name .. ".png", "wb")
  if file then file:write(png); file:close() end
end

emu.addEventCallback(function()
  frame = frame + 1
  while idx <= #SHOTS and SHOTS[idx].frame <= frame do
    save(string.format("%05d_%s", SHOTS[idx].frame, SHOTS[idx].name))
    idx = idx + 1
  end
  if idx > #SHOTS then emu.stop(0) end
end, emu.eventType.endFrame)
