-- Save a build-matched gameplay state immediately before opening Pause.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local saved = false
local save_callback

local function held(first, last) return frame >= first and frame <= last end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
  if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end
  if frame >= 5400 and frame <= 22500 and (frame % 30) <= 5 then buttons["a"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function arm()
  save_callback = emu.addMemoryCallback(function()
    if saved then return end
    local state = emu.createSavestate()
    local f = io.open(OUT_DIR .. "/pause_preentry.mss", "wb")
    if f then f:write(state); f:close(); saved = true end
    emu.removeMemoryCallback(save_callback)
  end, emu.callbackType.exec, 0x08000000, 0x09FFFFFF, emu.cpuType.gba, emu.memType.gbaMemory)
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 22850 then arm() end
  if frame >= 22870 and saved then emu.stop(0) end
end, emu.eventType.endFrame)
