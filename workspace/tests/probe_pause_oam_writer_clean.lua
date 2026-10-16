-- Trace CPU state while Pause label OAM entries are written on a clean route.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local lines = {}
local seen = {}

local function held(first, last) return frame >= first and frame <= last end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
  if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end
  if frame >= 5400 and frame <= 22500 and (frame % 30) <= 5 then buttons["a"] = true end
  if held(23000, 23007) then buttons["start"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function flatten(prefix, value, depth, out)
  if depth > 2 or type(value) ~= "table" then
    out[#out + 1] = prefix .. "=" .. tostring(value)
    return
  end
  for key, child in pairs(value) do flatten(prefix .. "." .. tostring(key), child, depth + 1, out) end
end

emu.addMemoryCallback(function(address, value)
  if frame < 22950 or frame > 23100 or address < 0x03000EA4 or address > 0x03000EEB then return end
  local fields = {}
  flatten("state", emu.getState(), 0, fields)
  table.sort(fields)
  local signature = table.concat(fields, " ")
  if not seen[signature] then
    seen[signature] = true
    lines[#lines + 1] = string.format("frame=%d iwram=0x%08X value=0x%02X %s", frame, address, value, signature)
  end
end, emu.callbackType.write, 0xEA4, 0xEEB, nil, emu.memType.gbaIntWorkRam)

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= 23120 then
    local f = io.open(OUT_DIR .. "/pause_oam_writers.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
