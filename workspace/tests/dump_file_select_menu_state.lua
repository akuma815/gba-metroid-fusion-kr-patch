-- Mesen 2 GBA: dump the first file-select popup at the same clean-boot frame.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0

local function dump(name, size, memType, base)
  local f = io.open(OUT_DIR .. "/" .. name, "wb")
  if not f then return end
  local chunk = {}
  base = base or 0
  for address = 0, size - 1 do
    chunk[#chunk + 1] = string.char(emu.read(base + address, memType))
    if #chunk == 4096 then
      f:write(table.concat(chunk)); chunk = {}
    end
  end
  if #chunk > 0 then f:write(table.concat(chunk)) end
  f:close()
end

emu.addEventCallback(function()
  local buttons = {}
  if (frame >= 3520 and frame <= 3527) or (frame >= 3720 and frame <= 3727) then
    buttons["start"] = true
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 3800 then
    local png = emu.takeScreenshot()
    local shot = io.open(OUT_DIR .. "/screen.png", "wb")
    if shot then shot:write(png); shot:close() end
    dump("vram.bin", 0x18000, emu.memType.gbaVideoRam)
    dump("palette.bin", 0x400, emu.memType.gbaPaletteRam)
    dump("oam.bin", 0x400, emu.memType.gbaSpriteRam)
    dump("io.bin", 0x60, emu.memType.gbaDebug, 0x04000000)
    emu.stop(0)
  end
end, emu.eventType.endFrame)
