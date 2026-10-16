-- Dump file-select OBJ VRAM after saved-slot information has been drawn.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0

local function held(first, last) return frame >= first and frame <= last end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520,3527) or held(3720,3727) then buttons.start=true end
  emu.setInput(buttons,0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 3650 then
    local values = {}
    for offset = 0, 0x7FFF do
      values[#values + 1] = string.char(
        emu.read(0x10000 + offset, emu.memType.gbaVideoRam))
    end
    local f = io.open(OUT_DIR .. "/file_select_obj_vram.bin", "wb")
    if f then f:write(table.concat(values)); f:close() end
    local png = emu.takeScreenshot()
    f = io.open(OUT_DIR .. "/03650_file_select.png", "wb")
    if f then f:write(png); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
