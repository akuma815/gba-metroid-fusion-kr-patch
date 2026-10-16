-- @@WATCH_START@@ is reused as the Japanese language mode selector: 0=adult, 1=child.
local OUT_DIR = "@@OUT_DIR@@"
local STATE_PATH = "@@STATE_PATH@@"
local LANGUAGE = @@WATCH_START@@
local frame = 0
local loaded = false
local load_callback

load_callback = emu.addMemoryCallback(function()
  if loaded then return end
  local file = assert(io.open(STATE_PATH, "rb"))
  local state = file:read("*all")
  file:close()
  emu.loadSavestate(state)
  loaded = true
  emu.removeMemoryCallback(load_callback)
end, emu.callbackType.exec, 0x08000000, 0x09FFFFFF,
    emu.cpuType.gba, emu.memType.gbaMemory)

emu.addEventCallback(function()
  frame = frame + 1
  if loaded and frame == 10 then
    emu.write(0x11, LANGUAGE, emu.memType.gbaIntWorkRam)
    emu.write(0x1344, 0, emu.memType.gbaIntWorkRam)
    emu.write(0x1345, 0, emu.memType.gbaIntWorkRam)
  end
  if loaded and frame == 480 then
    local file = assert(io.open(OUT_DIR .. "/0480.png", "wb"))
    file:write(emu.takeScreenshot())
    file:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
