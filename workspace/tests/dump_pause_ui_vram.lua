-- Dump live Pause-map and Status VRAM plus GBA BG registers.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0

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

local function dump(name)
  local chunks = {}
  for base = 0, 0x17FFF, 4096 do
    local values = {}
    for offset = 0, 4095 do
      values[#values + 1] = string.char(emu.read(base + offset, emu.memType.gbaVideoRam))
    end
    chunks[#chunks + 1] = table.concat(values)
  end
  local f = io.open(OUT_DIR .. "/" .. name .. "_vram.bin", "wb")
  if f then f:write(table.concat(chunks)); f:close() end
  local oam = {}
  for address = 0, 0x3FF do
    oam[#oam + 1] = string.char(emu.read(address, emu.memType.gbaSpriteRam))
  end
  f = io.open(OUT_DIR .. "/" .. name .. "_oam.bin", "wb")
  if f then f:write(table.concat(oam)); f:close() end
  local lines = {}
  for address = 0x04000000, 0x0400001F, 2 do
    lines[#lines + 1] = string.format("0x%08X=0x%04X", address,
      emu.read16(address, emu.memType.gbaDebug))
  end
  f = io.open(OUT_DIR .. "/" .. name .. "_regs.txt", "w")
  if f then f:write(table.concat(lines, "\n")); f:close() end
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 23100 then dump("map") end
  if frame == 23600 then dump("status"); emu.stop(0) end
end, emu.eventType.endFrame)
