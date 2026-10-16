-- Identify code that builds per-slot file information in OBJ VRAM.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local lines = {}
local seen = {}

local function held(first, last) return frame >= first and frame <= last end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520,3527) or held(3720,3727) then buttons.start=true end
  emu.setInput(buttons,0)
end, emu.eventType.inputPolled)

emu.addMemoryCallback(function(address, value)
  if frame > 3900 then return end
  local state = emu.getState()
  local cpu = state.cpu
  local pc = cpu.pipeline.execute.address
  local key = string.format("%08X:%05X", pc, address - (address % 32))
  if seen[key] then return end
  seen[key] = true
  lines[#lines + 1] = string.format(
    "frame=%d pc=0x%08X vram=0x%08X value=0x%02X r0=0x%08X r1=0x%08X r2=0x%08X r3=0x%08X r4=0x%08X r5=0x%08X r6=0x%08X r7=0x%08X",
    frame, pc, address, value, cpu.r0, cpu.r1, cpu.r2, cpu.r3,
    cpu.r4, cpu.r5, cpu.r6, cpu.r7)
end, emu.callbackType.write, 0x88C0, 0xA0BF, nil, emu.memType.gbaVideoRam)

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= 3900 then
    table.sort(lines)
    local f = io.open(OUT_DIR .. "/saved_file_select_vram_writers.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
