-- Identify the CPU renderer that reads glyph graphics for saved-slot metadata.
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local shot_index = 1
local lines = {}
local seen = {}

local function held(first, last) return frame >= first and frame <= last end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520,3527) or held(3720,3727) then buttons.start=true end
  emu.setInput(buttons,0)
end, emu.eventType.inputPolled)

emu.addMemoryCallback(function(address, value)
  if frame < 3500 or frame > 3900 then return end
  local state = emu.getState()
  local cpu = state.cpu
  local pc = cpu.pipeline.execute.address
  local key = string.format("%08X:%08X", pc, address - (address % 32))
  if seen[key] then return end
  seen[key] = true
  lines[#lines + 1] = string.format(
    "frame=%d pc=0x%08X glyph_read=0x%08X value=0x%02X r0=0x%08X r1=0x%08X r2=0x%08X r3=0x%08X r4=0x%08X r5=0x%08X r6=0x%08X r7=0x%08X",
    frame, pc, address, value, cpu.r0, cpu.r1, cpu.r2, cpu.r3,
    cpu.r4, cpu.r5, cpu.r6, cpu.r7)
end, emu.callbackType.read, 0x683AD8, 0x6B7FFF, nil, emu.memType.gbaPrgRom)

local function save(name)
  local png = emu.takeScreenshot()
  local f = io.open(OUT_DIR .. "/" .. name .. ".png", "wb")
  if f then f:write(png); f:close() end
end

emu.addEventCallback(function()
  frame = frame + 1
  while shot_index <= #SHOTS and SHOTS[shot_index].frame <= frame do
    save(string.format("%05d_%s", SHOTS[shot_index].frame, SHOTS[shot_index].name))
    shot_index = shot_index + 1
  end
  if frame >= 3900 then
    table.sort(lines)
    local f = io.open(OUT_DIR .. "/saved_file_select_font_calls.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
