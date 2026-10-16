-- Mesen 2 GBA: clean boot -> file select -> new game, then probe pause timing.
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local idx = 1

local function held(first, last)
  return frame >= first and frame <= last
end

emu.addEventCallback(function()
  local buttons = {}
  -- Title -> SAMUS DATA -> first slot's Game Start.
  if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
  if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end

  -- Advance dialogue pages; in gameplay these become harmless short A taps.
  if frame >= 5400 and frame <= 14500 and (frame % 30) <= 5 then buttons["a"] = true end

  -- Attempt pause only after the route should have reached controllable play.
  if held(15000, 15007) then buttons["start"] = true end
  if held(15400, 15407) then buttons["r"] = true end
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
