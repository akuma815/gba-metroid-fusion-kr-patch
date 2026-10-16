-- Enumerate contiguous ROM data reads during pause-map and status transitions.
local OUT_DIR = "@@OUT_DIR@@"
local MAX_FRAME = @@MAX_FRAME@@
local frame = 0
local installed = false
local phases = {
  map_entry = {first = 15000, last = 15200, reads = {}},
  status_entry = {first = 15400, last = 15600, reads = {}},
}

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

local function installCallback()
  if installed then return end
  installed = true
  emu.addMemoryCallback(function(addr, value)
    local _, phase = phaseNow()
    if phase then phase.reads[addr] = true end
  end, emu.callbackType.read, 0x000000, 0x7FFFFF, nil, emu.memType.gbaPrgRom)
end

local function sortedKeys(values)
  local result = {}
  for value, _ in pairs(values) do result[#result + 1] = value end
  table.sort(result)
  return result
end

local function ranges(values)
  local keys = sortedKeys(values)
  local result = {}
  if #keys == 0 then return keys, result end
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
  return keys, result
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 14990 then installCallback() end
  if frame >= MAX_FRAME then
    local lines = {string.format("frames=0-%d", frame)}
    for _, name in ipairs({"map_entry", "status_entry"}) do
      local phase = phases[name]
      local keys, runs = ranges(phase.reads)
      lines[#lines + 1] = string.format("%s frames=%d-%d unique_reads=%d contiguous_runs=%d",
        name, phase.first, phase.last, #keys, #runs)
      for _, run in ipairs(runs) do
        local length = run.last - run.first + 1
        if length >= 4 then
          lines[#lines + 1] = string.format("  0x%08X-0x%08X length=%d", run.first, run.last, length)
        end
      end
    end
    local f = io.open(OUT_DIR .. "/probe_pause_rom_reads.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    for _, line in ipairs(lines) do emu.log(line) end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
