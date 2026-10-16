-- Dump RAM and OAM on the first stable Pause-map frame.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0

local function held(first, last) return frame >= first and frame <= last end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
  if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end
  if frame >= 5400 and frame <= 22500 and (frame % 30) <= 5 then buttons["a"] = true end
  if held(23000, 23007) then buttons["start"] = true end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function dump_memory(name, size, memtype)
  local f = assert(io.open(OUT_DIR .. "/" .. name, "wb"))
  for base = 0, size - 1, 4096 do
    local values = {}
    for offset = 0, math.min(4095, size - base - 1) do
      values[#values + 1] = string.char(emu.read(base + offset, memtype))
    end
    f:write(table.concat(values))
  end
  f:close()
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 23100 then
    dump_memory("map_ewram.bin", 0x40000, emu.memType.gbaExtWorkRam)
    dump_memory("map_iwram.bin", 0x8000, emu.memType.gbaIntWorkRam)
    dump_memory("map_oam.bin", 0x400, emu.memType.gbaSpriteRam)
    emu.stop(0)
  end
end, emu.eventType.endFrame)
