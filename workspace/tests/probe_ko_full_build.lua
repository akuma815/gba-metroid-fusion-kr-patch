-- Connect the full Korean QA build's pointer, relocated text, and font reads.
local OUT_DIR = "@@OUT_DIR@@"
local MAX_FRAME = @@MAX_FRAME@@
local frame = 0
local pointerReads = {}
local textReads = {}
local fontReads = {}

local function record(set, addr)
  set[addr] = true
end

-- Japanese and Japanese-Hiragana file-select pointer tables.
emu.addMemoryCallback(function(addr, value)
  if frame >= 300 and frame <= 900 then record(pointerReads, addr) end
end, emu.callbackType.read, 0x7F1118, 0x7F11FF, nil, emu.memType.gbaPrgRom)

-- Exact used ranges from build/metroid_fusion_ko_full_qa.json.
for _, range in ipairs({
  {0x6B0AD8, 0x6B2793},
  {0x6B9894, 0x6C1131},
  {0x6C113A, 0x6C3685},
}) do
  emu.addMemoryCallback(function(addr, value)
    record(textReads, addr)
  end, emu.callbackType.read, range[1], range[2], nil, emu.memType.gbaPrgRom)
end

-- Physical font span occupied by the mapped 9x12 Korean payload.
emu.addMemoryCallback(function(addr, value)
  record(fontReads, addr)
end, emu.callbackType.read, 0x686318, 0x6AA1D7, nil, emu.memType.gbaPrgRom)

local function pulse(buttons, name, first, last)
  if frame >= first and frame <= last then buttons[name] = true end
end

emu.addEventCallback(function()
  local buttons = {}
  pulse(buttons, "start", 120, 127)
  pulse(buttons, "start", 300, 307)
  pulse(buttons, "a", 520, 527)
  pulse(buttons, "a", 760, 767)
  pulse(buttons, "a", 1000, 1007)
  pulse(buttons, "start", 1240, 1247)
  pulse(buttons, "a", 1500, 1507)
  pulse(buttons, "a", 1760, 1767)
  pulse(buttons, "a", 2050, 2057)
  pulse(buttons, "a", 2350, 2357)
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function stats(values)
  local count = 0
  local minimum = nil
  local maximum = nil
  for value, _ in pairs(values) do
    count = count + 1
    if minimum == nil or value < minimum then minimum = value end
    if maximum == nil or value > maximum then maximum = value end
  end
  return count, minimum or 0, maximum or 0
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= MAX_FRAME then
    local pointerCount, pointerMin, pointerMax = stats(pointerReads)
    local textCount, textMin, textMax = stats(textReads)
    local fontCount, fontMin, fontMax = stats(fontReads)
    local lines = {
      string.format("frames=0-%d", frame),
      string.format("file_select_pointer_read_addresses=%d", pointerCount),
      string.format("file_select_pointer_read_range=0x%08X-0x%08X", pointerMin, pointerMax),
      string.format("relocated_text_read_addresses=%d", textCount),
      string.format("relocated_text_read_range=0x%08X-0x%08X", textMin, textMax),
      string.format("mapped_font_read_addresses=%d", fontCount),
      string.format("mapped_font_read_range=0x%08X-0x%08X", fontMin, fontMax),
    }
    local file = io.open(OUT_DIR .. "/probe_ko_full_build.txt", "w")
    if file then file:write(table.concat(lines, "\n")); file:close() end
    for _, line in ipairs(lines) do emu.log(line) end
    if pointerCount == 0 or textCount == 0 or fontCount == 0 then
      emu.stop(1)
    else
      emu.stop(0)
    end
  end
end, emu.eventType.endFrame)

emu.log("probe_ko_full_build started")
