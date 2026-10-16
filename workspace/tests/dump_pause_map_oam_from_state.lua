-- Load a build-matched gameplay state, open Pause, and dump the live map OAM.
local OUT_DIR = "@@OUT_DIR@@"
local STATE_PATH = "@@STATE_PATH@@"
local frame = 0
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
  if frame >= 20 and frame <= 27 then buttons["start"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame == 120 then
    local oam = {}
    for address = 0, 0x3FF do
      oam[#oam + 1] = string.char(emu.read(address, emu.memType.gbaSpriteRam))
    end
    local file = assert(io.open(OUT_DIR .. "/map_oam.bin", "wb"))
    file:write(table.concat(oam))
    file:close()
    file = assert(io.open(OUT_DIR .. "/map.png", "wb"))
    file:write(emu.takeScreenshot())
    file:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
