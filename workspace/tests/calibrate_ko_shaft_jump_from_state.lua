-- Load the verified shaft-bottom state and calibrate a higher/longer first jump.
local OUT_DIR = "@@OUT_DIR@@"
local STATE_PATH = "@@STATE_PATH@@"
local SHOTS = @@SHOTS@@
local frame = 0
local idx = 1
local loaded = false
local load_callback = nil

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

local function save(name)
  local png = emu.takeScreenshot()
  local path = OUT_DIR .. "/" .. name .. ".png"
  local file = io.open(path, "wb")
  if file then file:write(png); file:close(); emu.log("saved " .. path) end
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  while idx <= #SHOTS and SHOTS[idx].frame <= frame do
    save(string.format("%05d_%s", SHOTS[idx].frame, SHOTS[idx].name))
    idx = idx + 1
  end
  if idx > #SHOTS then emu.stop(0) end
end, emu.eventType.endFrame)
