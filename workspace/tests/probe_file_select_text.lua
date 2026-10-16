-- Connect file-select ROM text reads to main-font reads during a clean-boot visit.
local OUT_DIR = "@@OUT_DIR@@"
local MAX_FRAME = @@MAX_FRAME@@
local frame = 0
local textReads = {}
local fontCodes = {}

emu.addMemoryCallback(function(addr, value)
  if frame >= 3500 then textReads[addr] = true end
end, emu.callbackType.read, 0x745FAC, 0x7486CE, nil, emu.memType.gbaPrgRom)

emu.addMemoryCallback(function(addr, value)
  if frame >= 3500 then
    local tile = math.floor((addr - 0x08683AD8) / 32)
    local code = tile
    if (math.floor(tile / 32) % 2) == 1 then code = tile - 32 end
    fontCodes[code] = true
  end
end, emu.callbackType.read, 0x683AD8, 0x6B8000, nil, emu.memType.gbaPrgRom)

emu.addEventCallback(function()
  local buttons = {}
  if (frame >= 3520 and frame <= 3527) or (frame >= 3720 and frame <= 3727) then
    buttons["start"] = true
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function sortedKeys(values)
  local result = {}
  for value, _ in pairs(values) do result[#result + 1] = value end
  table.sort(result)
  return result
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= MAX_FRAME then
    local textList = sortedKeys(textReads)
    local codeList = sortedKeys(fontCodes)
    local lines = {
      string.format("frames=3500-%d", frame),
      string.format("unique_text_read_addresses=%d", #textList),
      string.format("text_runtime_range=0x%08X-0x%08X", textList[1] or 0, textList[#textList] or 0),
      string.format("unique_font_codes=%d", #codeList),
    }
    local parts = {}
    for _, code in ipairs(codeList) do parts[#parts + 1] = string.format("%04X", code) end
    lines[#lines + 1] = "font_codes=" .. table.concat(parts, " ")
    local f = io.open(OUT_DIR .. "/probe_file_select_text.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    for _, line in ipairs(lines) do emu.log(line) end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
