-- Load the verified shaft-bottom state, climb to the upper central platform,
-- and create a reusable Mesen savestate for later Navigation Room QA.
local OUT_DIR = "@@OUT_DIR@@"
local STATE_PATH = "@@STATE_PATH@@"
local SHOTS = @@SHOTS@@
local frame = 0
local idx = 1
local loaded = false
local saved = false
local load_callback = nil
local save_callback = nil

local state_file = assert(io.open(STATE_PATH, "rb"))
local state_data = state_file:read("*a")
state_file:close()

load_callback = emu.addMemoryCallback(function()
  if not loaded then
    loaded = true
    emu.loadSavestate(state_data)
    emu.removeMemoryCallback(load_callback)
  end
end, emu.callbackType.exec, 0x08000000, 0x09FFFFFF, emu.cpuType.gba, emu.memType.gbaMemory)

emu.addEventCallback(function()
  local buttons = {}
  if frame >= 5 and frame <= 60 then buttons["right"] = true end
  if frame >= 25 and frame <= 43 then buttons["a"] = true end
  if frame >= 90 and frame <= 130 then buttons["right"] = true end
  if frame >= 90 and frame <= 108 then buttons["a"] = true end
  if frame >= 150 and frame <= 185 then buttons["left"] = true end
  if frame >= 150 and frame <= 168 then buttons["a"] = true end
  if frame >= 210 and frame <= 220 then buttons["left"] = true end
  if frame >= 230 and frame <= 248 then buttons["a"] = true end
  if frame >= 230 and frame <= 270 then buttons["left"] = true end
  if frame >= 274 and frame <= 276 then buttons["a"] = true end
  if frame >= 271 and frame <= 276 then buttons["right"] = true end
  if frame >= 277 and frame <= 285 then buttons["left"] = true end
  if frame >= 290 and frame <= 305 then buttons["up"] = true end
  if frame >= 310 and frame <= 328 then buttons["a"] = true end
  if frame >= 310 and frame <= 350 then buttons["right"] = true end
  if frame >= 355 and frame <= 370 then buttons["up"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function save_screenshot(name)
  local png = emu.takeScreenshot()
  local file = io.open(OUT_DIR .. "/" .. name .. ".png", "wb")
  if file then file:write(png); file:close() end
end

local function arm_savestate_capture()
  save_callback = emu.addMemoryCallback(function()
    if not saved then
      local state = emu.createSavestate()
      local file = io.open(OUT_DIR .. "/ko_full_shaft_upper_platform.mss", "wb")
      if file then
        file:write(state)
        file:close()
        saved = true
        emu.log("saved reusable upper-platform state")
      end
      emu.removeMemoryCallback(save_callback)
    end
  end, emu.callbackType.exec, 0x08000000, 0x09FFFFFF, emu.cpuType.gba, emu.memType.gbaMemory)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame == 400 then arm_savestate_capture() end
  while idx <= #SHOTS and SHOTS[idx].frame <= frame do
    save_screenshot(string.format("%05d_%s", SHOTS[idx].frame, SHOTS[idx].name))
    idx = idx + 1
  end
  if saved and idx > #SHOTS then emu.stop(0) end
end, emu.eventType.endFrame)
