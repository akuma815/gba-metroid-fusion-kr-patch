-- Identify the routines and source registers that populate title BG VRAM.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local lines = {}
local seen = {}

emu.addMemoryCallback(function(address, value)
  if frame > 3450 then return end
  local state = emu.getState()
  local cpu = state.cpu
  local pc = cpu.pipeline.execute.address
  local block = address - (address % 32)
  local key = string.format("%08X:%05X", pc, block)
  if seen[key] then return end
  seen[key] = true
  lines[#lines + 1] = string.format(
    "frame=%d pc=0x%08X vram=0x%05X value=0x%02X r0=0x%08X r1=0x%08X r2=0x%08X r3=0x%08X r4=0x%08X r5=0x%08X r6=0x%08X r7=0x%08X",
    frame, pc, address, value, cpu.r0, cpu.r1, cpu.r2, cpu.r3,
    cpu.r4, cpu.r5, cpu.r6, cpu.r7)
end, emu.callbackType.write, 0x0000, 0xFFFF, nil, emu.memType.gbaVideoRam)

emu.addEventCallback(function()
  frame = frame + 1
  if frame >= 3451 then
    local f = io.open(OUT_DIR .. "/title_vram_writers.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
