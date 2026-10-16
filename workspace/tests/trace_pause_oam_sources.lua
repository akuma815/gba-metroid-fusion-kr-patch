-- Record the ROM source halfword used for each live Pause-map/Status OBJ attr2.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local lines = {}

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

emu.addMemoryCallback(function(address, value)
  if not ((frame >= 23099 and frame <= 23101) or (frame >= 23599 and frame <= 23601)) then return end
  local relative = address - 0x03000E1C
  if relative < 0 or relative >= 0x400 or (relative % 8) ~= 4 then return end
  local state = emu.getState()
  local cpu = state.cpu
  local pc = cpu.pipeline.execute.address
  -- The generic OAM builders use r4 or r9 as the ROM-side source cursor.
  lines[#lines + 1] = string.format(
    "frame=%d entry=%d dest=0x%08X value=0x%04X pc=0x%08X r4=0x%08X r9=0x%08X",
    frame, math.floor(relative / 8), address, value, pc, cpu.r4, cpu.r9)
end, emu.callbackType.write, 0xEA4, 0xF73, nil, emu.memType.gbaIntWorkRam)

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= 23602 then
    local f = io.open(OUT_DIR .. "/pause_oam_sources.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
