-- Dump BG VRAM and palette at selected clean-boot frames.
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local index = 1

local function dumpMemory(path, size, memType)
  local chunks = {}
  for base = 0, size - 1, 4096 do
    local values = {}
    local last = math.min(base + 4095, size - 1)
    for address = base, last do
      values[#values + 1] = string.char(emu.read(address, memType))
    end
    chunks[#chunks + 1] = table.concat(values)
  end
  local f = io.open(path, "wb")
  if f then f:write(table.concat(chunks)); f:close() end
end

emu.addEventCallback(function()
  frame = frame + 1
  while index <= #SHOTS and SHOTS[index].frame <= frame do
    local stem = string.format("%05d", SHOTS[index].frame)
    dumpMemory(OUT_DIR .. "/" .. stem .. "_vram.bin", 0x10000, emu.memType.gbaVideoRam)
    dumpMemory(OUT_DIR .. "/" .. stem .. "_palette.bin", 0x200, emu.memType.gbaPaletteRam)
    index = index + 1
  end
  if index > #SHOTS then emu.stop(0) end
end, emu.eventType.endFrame)
