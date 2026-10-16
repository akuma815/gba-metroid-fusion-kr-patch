-- Create a reusable Mesen savestate at the bottom of the first Docking Bay shaft.
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local idx = 1
local saved = false
local save_callback = nil

local function held(first, last)
  return frame >= first and frame <= last
end

emu.addEventCallback(function()
  local buttons = {}
  if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
  if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end
  if frame >= 5400 and frame <= 22500 and (frame % 30) <= 5 then buttons["a"] = true end
  if held(22600, 23480) then buttons["left"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function save(name)
  local png = emu.takeScreenshot()
  local path = OUT_DIR .. "/" .. name .. ".png"
  local file = io.open(path, "wb")
  if file then file:write(png); file:close(); emu.log("saved " .. path) end
end

local function arm_savestate_capture()
  save_callback = emu.addMemoryCallback(function()
    if not saved then
      local state = emu.createSavestate()
      local file = io.open(OUT_DIR .. "/ko_full_shaft_bottom.mss", "wb")
      if file then
        file:write(state)
        file:close()
        saved = true
        emu.log("saved reusable shaft state")
      end
      emu.removeMemoryCallback(save_callback)
    end
  end, emu.callbackType.exec, 0x08000000, 0x09FFFFFF, emu.cpuType.gba, emu.memType.gbaMemory)
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 23490 then arm_savestate_capture() end
  while idx <= #SHOTS and SHOTS[idx].frame <= frame do
    save(string.format("%05d_%s", SHOTS[idx].frame, SHOTS[idx].name))
    idx = idx + 1
  end
  if idx > #SHOTS and saved then emu.stop(0) end
end, emu.eventType.endFrame)
