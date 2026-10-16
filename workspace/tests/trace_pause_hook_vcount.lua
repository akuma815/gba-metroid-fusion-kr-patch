-- Record scanlines on which the injected Pause runtime hook executes.
local OUT_DIR = "@@OUT_DIR@@"
local MAX_FRAME = @@MAX_FRAME@@
local frame = 0
local counts = {}

local function held(first, last) return frame >= first and frame <= last end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520,3527) or held(3720,3727) then buttons.start=true end
  if held(3920,3927) or held(4200,4207) or held(4600,4607) then buttons.a=true end
  if frame >= 5400 and frame <= 22500 and (frame % 30) <= 5 then buttons.a=true end
  if held(23000,23007) then buttons.start=true end
  if held(23500,23507) then buttons.r=true end
  emu.setInput(buttons,0)
end, emu.eventType.inputPolled)

emu.addMemoryCallback(function()
  if frame >= 22800 then
    local vcount = emu.read16(0x04000006, emu.memType.gbaDebug)
    local key = string.format("frame=%d vcount=%d", frame, vcount)
    counts[key] = (counts[key] or 0) + 1
  end
end, emu.callbackType.exec, 0x0807921E, 0x08079221,
  emu.cpuType.gba, emu.memType.gbaMemory)

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= MAX_FRAME then
    local keys = {}
    for key in pairs(counts) do keys[#keys + 1] = key end
    table.sort(keys)
    local lines = {}
    for _, key in ipairs(keys) do lines[#lines + 1] = key .. " calls=" .. counts[key] end
    local f = io.open(OUT_DIR .. "/pause_hook_vcount.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
