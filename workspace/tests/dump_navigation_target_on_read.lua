-- Dump the navigation map message state when message/ja/043 is visible.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local trigger_frame = nil

emu.addMemoryCallback(function()
  if not trigger_frame then trigger_frame = frame end
end, emu.callbackType.read, @@WATCH_START@@, @@WATCH_END@@, nil, emu.memType.gbaPrgRom)

local function held(first, last)
  return frame >= first and frame <= last
end

emu.addEventCallback(function()
  local buttons = {}
  if not trigger_frame then
    if held(3520, 3527) or held(3720, 3727) then buttons["start"] = true end
    if held(3920, 3927) or held(4200, 4207) or held(4600, 4607) then buttons["a"] = true end
    if frame >= 5400 and (frame % 30) <= 5 then buttons["a"] = true end
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function dump(name, size, memType)
  local f = io.open(OUT_DIR .. "/" .. name, "wb")
  if not f then return end
  local bytes = {}
  for address = 0, size - 1 do
    bytes[#bytes + 1] = string.char(emu.read(address, memType))
    if #bytes == 4096 then f:write(table.concat(bytes)); bytes = {} end
  end
  if #bytes > 0 then f:write(table.concat(bytes)) end
  f:close()
end

emu.addEventCallback(function()
  frame = frame + 1
  if trigger_frame and frame == trigger_frame + 160 then
    local f = io.open(OUT_DIR .. "/screen.png", "wb")
    if f then f:write(emu.takeScreenshot()); f:close() end
    dump("vram.bin", 0x18000, emu.memType.gbaVideoRam)
    dump("palette.bin", 0x400, emu.memType.gbaPaletteRam)
    dump("oam.bin", 0x400, emu.memType.gbaSpriteRam)
    emu.stop(0)
  elseif frame >= 24000 then
    emu.stop(1)
  end
end, emu.eventType.endFrame)
