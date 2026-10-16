-- Load a build-matched gameplay state, force Samus' energy to zero, then
-- capture the Game Over screen and its complete GBA VRAM image.
local OUT_DIR = "@@OUT_DIR@@"
local STATE_PATH = "@@STATE_PATH@@"
local frame = 0
local loaded = false
local killed = false
local load_callback

local function dump(name, size, mem_type)
  local chunks = {}
  for address = 0, size - 1 do
    chunks[#chunks + 1] = string.char(emu.read(address, mem_type))
  end
  local file = io.open(OUT_DIR .. "/" .. name, "wb")
  if file then file:write(table.concat(chunks)); file:close() end
end

local function screenshot(name)
  local file = io.open(OUT_DIR .. "/" .. name .. ".png", "wb")
  if file then file:write(emu.takeScreenshot()); file:close() end
end

load_callback = emu.addMemoryCallback(function()
  if loaded then return end
  local file = io.open(STATE_PATH, "rb")
  if not file then error("cannot open state: " .. STATE_PATH) end
  local state = file:read("*all")
  file:close()
  emu.loadSavestate(state)
  loaded = true
  emu.removeMemoryCallback(load_callback)
end, emu.callbackType.exec, 0x08000000, 0x09FFFFFF,
    emu.cpuType.gba, emu.memType.gbaMemory)

emu.addEventCallback(function()
  frame = frame + 1
  if loaded and frame == 10 and not killed then
    emu.write(0x1344, 0, emu.memType.gbaIntWorkRam)
    emu.write(0x1345, 0, emu.memType.gbaIntWorkRam)
    killed = true
    emu.log("forced energy to zero")
  end
  if loaded and (frame == 120 or frame == 240 or frame == 360 or frame == 480 or frame == 600) then
    screenshot(string.format("%04d", frame))
  end
  if loaded and frame == 600 then
    dump("vram.bin", 0x18000, emu.memType.gbaVideoRam)
    dump("palette.bin", 0x400, emu.memType.gbaPaletteRam)
    emu.stop(0)
  end
end, emu.eventType.endFrame)
