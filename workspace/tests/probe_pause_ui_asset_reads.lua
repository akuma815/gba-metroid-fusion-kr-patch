-- Prove whether Pause/Status consumes original or relocated UI streams.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local counts = {}
local first = {}
local function hit(name)
  if frame < 22800 then return end
  counts[name] = (counts[name] or 0) + 1
  if not first[name] then first[name] = frame end
end

local function held(first, last) return frame >= first and frame <= last end

emu.addEventCallback(function()
  local buttons = {}
  if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
  if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end
  if frame >= 5400 and frame <= 22500 and (frame % 30) <= 5 then buttons["a"] = true end
  if held(23000, 23007) then buttons["start"] = true end
  if held(23500, 23507) then buttons["r"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local ranges = {
  {"source_status_tiles", 0x56C930, 0x56EF41},
  {"source_map_tiles", 0x571DF8, 0x575324},
  {"source_maps", 0x576800, 0x57744A},
  {"target_status_tiles", 0x6C2DE4, 0x6C559F},
  {"target_map_tiles", 0x6C55A8, 0x6C8C67},
  {"target_maps", 0x6C8C68, 0x6C988F},
}
for _, item in ipairs(ranges) do
  local name = item[1]
  emu.addMemoryCallback(function() hit(name) end,
    emu.callbackType.read, item[2], item[3], nil, emu.memType.gbaPrgRom)
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= 23700 then
    local parts = {}
    for _, item in ipairs(ranges) do
      local name = item[1]
      parts[#parts + 1] = string.format("%s=%d first=%s", name, counts[name] or 0,
        first[name] and tostring(first[name]) or "none")
    end
    local line = table.concat(parts, "\n")
    local f = io.open(OUT_DIR .. "/pause_ui_asset_reads.txt", "w")
    if f then f:write(line); f:close() end
    emu.log(line)
    emu.stop(0)
  end
end, emu.eventType.endFrame)
