-- Explore the upper Docking Bay shaft from the verified central-platform state.
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
  if frame >= 10 and frame <= 32 then buttons["a"] = true end
  if frame >= 10 and frame <= 58 then buttons["left"] = true end
  if frame >= 50 and frame <= 65 then buttons["up"] = true end
  if frame >= 80 and frame <= 102 then buttons["a"] = true end
  if frame >= 80 and frame <= 128 then buttons["right"] = true end
  if frame >= 160 and frame <= 182 then buttons["a"] = true end
  if frame >= 150 and frame <= 205 then buttons["right"] = true end
  if frame >= 209 and frame <= 225 then buttons["a"] = true end
  if frame >= 206 and frame <= 255 then buttons["left"] = true end
  if frame >= 260 and frame <= 280 then buttons["up"] = true end
  if frame >= 300 and frame <= 322 then buttons["a"] = true end
  if frame >= 300 and frame <= 350 then buttons["left"] = true end
  if frame >= 370 and frame <= 390 then buttons["right"] = true end
  if frame >= 410 and frame <= 432 then buttons["a"] = true end
  if frame >= 410 and frame <= 460 then buttons["right"] = true end
  if frame >= 510 and frame <= 532 then buttons["a"] = true end
  if frame >= 510 and frame <= 565 then buttons["left"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function save(name)
  local png = emu.takeScreenshot()
  local file = io.open(OUT_DIR .. "/" .. name .. ".png", "wb")
  if file then file:write(png); file:close() end
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
