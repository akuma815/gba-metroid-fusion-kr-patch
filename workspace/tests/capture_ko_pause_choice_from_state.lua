-- Reproduce the pause-map objective confirmation overlay from a gameplay state.
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

local function held(first, last)
  return frame >= first and frame <= last
end

emu.addEventCallback(function()
  local buttons = {}
  if held(20, 27) then buttons["start"] = true end
  -- Open/close the objective text, then activate SLEEP without leaving Pause.
  -- This reproduces the stale-tile sequence reported during manual QA.
  if held(160, 167) then buttons["a"] = true end
  if held(320, 327) then buttons["a"] = true end
  if held(460, 467) then buttons["l"] = true end
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
