-- Connect a clean-boot pause transition to Japanese text/meta and main-font reads.
local OUT_DIR = "@@OUT_DIR@@"
local MAX_FRAME = @@MAX_FRAME@@
local frame = 0
local phases = {
  before = {first = 14400, last = 14999, text = {}, meta = {}, font = {}},
  map_entry = {first = 15000, last = 15200, text = {}, meta = {}, font = {}},
  map_steady = {first = 15201, last = 15399, text = {}, meta = {}, font = {}},
  status_entry = {first = 15400, last = 15600, text = {}, meta = {}, font = {}},
  status_steady = {first = 15601, last = 16000, text = {}, meta = {}, font = {}},
}
local callbacksInstalled = false

local function held(first, last) return frame >= first and frame <= last end
local function phaseNow()
  for name, phase in pairs(phases) do
    if frame >= phase.first and frame <= phase.last then return name, phase end
  end
  return nil, nil
end

emu.addEventCallback(function()
  local buttons = {}
  if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
  if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end
  if frame >= 5400 and frame <= 14500 and (frame % 30) <= 5 then buttons["a"] = true end
  if held(15000, 15007) then buttons["start"] = true end
  if held(15400, 15407) then buttons["r"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function installCallbacks()
  if callbacksInstalled then return end
  callbacksInstalled = true
  emu.addMemoryCallback(function(addr, value)
    local _, phase = phaseNow()
    if phase then phase.text[addr] = true end
  end, emu.callbackType.read, 0x6B0AD8, 0x6B1747, nil, emu.memType.gbaPrgRom)

  emu.addMemoryCallback(function(addr, value)
    local _, phase = phaseNow()
    if phase then phase.meta[addr] = true end
  end, emu.callbackType.read, 0x7EEC5C, 0x7EF4AB, nil, emu.memType.gbaPrgRom)

  emu.addMemoryCallback(function(addr, value)
    local _, phase = phaseNow()
    if phase then phase.font[addr] = true end
  end, emu.callbackType.read, 0x683AD8, 0x6AFFFF, nil, emu.memType.gbaPrgRom)
end

local function sortedKeys(values)
  local result = {}
  for value, _ in pairs(values) do result[#result + 1] = value end
  table.sort(result)
  return result
end

local function range(values)
  local list = sortedKeys(values)
  if #list == 0 then return "none" end
  return string.format("0x%08X-0x%08X", list[1], list[#list])
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 14390 then installCallbacks() end
  if frame >= MAX_FRAME then
    local lines = {string.format("frames=0-%d", frame)}
    for _, name in ipairs({"before", "map_entry", "map_steady", "status_entry", "status_steady"}) do
      local phase = phases[name]
      local text = sortedKeys(phase.text)
      local meta = sortedKeys(phase.meta)
      local font = sortedKeys(phase.font)
      lines[#lines + 1] = string.format(
        "%s frames=%d-%d text_reads=%d text_range=%s meta_reads=%d meta_range=%s font_reads=%d font_range=%s",
        name, phase.first, phase.last, #text, range(phase.text), #meta, range(phase.meta), #font, range(phase.font))
    end
    local f = io.open(OUT_DIR .. "/probe_pause_text.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    for _, line in ipairs(lines) do emu.log(line) end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
