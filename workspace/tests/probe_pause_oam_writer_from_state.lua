-- Trace CPU state while Pause label OAM entries are written.
local OUT_DIR = "@@OUT_DIR@@"
local STATE_PATH = "@@STATE_PATH@@"
local frame = 0
local loaded = false
local lines = {}
local seen = {}

local sf = assert(io.open(STATE_PATH, "rb"))
local state_data = sf:read("*a")
sf:close()

local load_callback
load_callback = emu.addMemoryCallback(function()
  if not loaded then
    loaded = true
    emu.loadSavestate(state_data)
    emu.removeMemoryCallback(load_callback)
  end
end, emu.callbackType.exec, 0x08000000, 0x09FFFFFF, emu.cpuType.gba, emu.memType.gbaMemory)

local function flatten(prefix, value, depth, out)
  if depth > 2 or type(value) ~= "table" then
    out[#out + 1] = prefix .. "=" .. tostring(value)
    return
  end
  for key, child in pairs(value) do
    flatten(prefix .. "." .. tostring(key), child, depth + 1, out)
  end
end

emu.addMemoryCallback(function(address, value)
  if not loaded or frame < 15 or frame > 100 then return end
  -- Top chrome labels occupy OAM entries 17-25 (byte offsets 0x88-0xCF).
  if address < 0x88 or address > 0xCF then return end
  local state = emu.getState()
  local fields = {}
  flatten("state", state, 0, fields)
  local signature = table.concat(fields, " ")
  if not seen[signature] then
    seen[signature] = true
    lines[#lines + 1] = string.format("frame=%d oam=0x%03X value=0x%02X %s",
      frame, address, value, signature)
  end
end, emu.callbackType.write, 0x88, 0xCF, nil, emu.memType.gbaSpriteRam)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  local buttons = {}
  if frame >= 20 and frame <= 27 then buttons["start"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if not loaded then return end
  if frame >= 140 then
    local f = io.open(OUT_DIR .. "/pause_oam_writers.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
