-- Capture the clean-boot title screen and the data read while it is assembled.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local reads = {}

emu.addMemoryCallback(function(addr, value)
  if frame >= 3000 and frame <= 3450 then reads[addr] = true end
end, emu.callbackType.read, 0x000000, 0x7FFFFF, nil, emu.memType.gbaPrgRom)

local function dumpMemory(name, size, memType)
  local chunks = {}
  for base = 0, size - 1, 4096 do
    local values = {}
    local last = math.min(base + 4095, size - 1)
    for address = base, last do
      values[#values + 1] = string.char(emu.read(address, memType))
    end
    chunks[#chunks + 1] = table.concat(values)
  end
  local f = io.open(OUT_DIR .. "/" .. name, "wb")
  if f then f:write(table.concat(chunks)); f:close() end
end

local function sortedKeys(values)
  local result = {}
  for value, _ in pairs(values) do result[#result + 1] = value end
  table.sort(result)
  return result
end

local function readRanges()
  local keys = sortedKeys(reads)
  local result = {}
  if #keys == 0 then return result end
  local first, last = keys[1], keys[1]
  for i = 2, #keys do
    local value = keys[i]
    if value == last + 1 then
      last = value
    else
      result[#result + 1] = {first = first, last = last}
      first, last = value, value
    end
  end
  result[#result + 1] = {first = first, last = last}
  return result
end

local function dump()
  local png = emu.takeScreenshot()
  local f = io.open(OUT_DIR .. "/title.png", "wb")
  if f then f:write(png); f:close() end
  dumpMemory("title_vram.bin", 0x18000, emu.memType.gbaVideoRam)
  dumpMemory("title_palette.bin", 0x400, emu.memType.gbaPaletteRam)
  dumpMemory("title_oam.bin", 0x400, emu.memType.gbaSpriteRam)

  local lines = {"frame=3450"}
  for address = 0x04000000, 0x04000055, 2 do
    lines[#lines + 1] = string.format("reg 0x%08X=0x%04X", address,
      emu.read16(address, emu.memType.gbaDebug))
  end
  for _, run in ipairs(readRanges()) do
    local length = run.last - run.first + 1
    if length >= 4 then
      lines[#lines + 1] = string.format("read 0x%06X-0x%06X length=%d", run.first, run.last, length)
    end
  end
  f = io.open(OUT_DIR .. "/title_state.txt", "w")
  if f then f:write(table.concat(lines, "\n")); f:close() end
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 3450 then dump(); emu.stop(0) end
end, emu.eventType.endFrame)
