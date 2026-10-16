-- Split ROM reads into short buckets around the title-screen VRAM load.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local buckets = {}

emu.addMemoryCallback(function(address, value)
  if frame < 3180 or frame > 3420 then return end
  local first = math.floor(frame / 20) * 20
  local bucket = buckets[first]
  if not bucket then bucket = {}; buckets[first] = bucket end
  bucket[address] = true
end, emu.callbackType.read, 0x000000, 0x7FFFFF, nil, emu.memType.gbaPrgRom)

local function sortedKeys(values)
  local result = {}
  for value, _ in pairs(values) do result[#result + 1] = value end
  table.sort(result)
  return result
end

local function appendRanges(lines, first, values)
  local keys = sortedKeys(values)
  if #keys == 0 then return end
  local start, last = keys[1], keys[1]
  for i = 2, #keys + 1 do
    local value = keys[i]
    if value and value == last + 1 then
      last = value
    else
      local length = last - start + 1
      if length >= 4 then
        lines[#lines + 1] = string.format("frames=%d-%d read=0x%08X-0x%08X length=%d",
          first, first + 19, start, last, length)
      end
      if value then start, last = value, value end
    end
  end
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= 3421 then
    local lines = {}
    for first = 3180, 3420, 20 do appendRanges(lines, first, buckets[first] or {}) end
    local f = io.open(OUT_DIR .. "/title_rom_reads.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
