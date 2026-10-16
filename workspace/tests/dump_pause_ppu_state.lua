local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local function held(a,b) return frame >= a and frame <= b end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520,3527) or held(3720,3727) then buttons.start=true end
  if held(3920,3927) or held(4200,4207) or held(4600,4607) then buttons.a=true end
  if frame >= 5400 and frame <= 22500 and (frame % 30) <= 5 then buttons.a=true end
  if held(23000,23007) then buttons.start=true end
  if held(23500,23507) then buttons.r=true end
  emu.setInput(buttons,0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  frame=frame+1
  if frame==23100 or frame==23600 then
    local s=emu.getState()
    local out={}
    for i,b in pairs(s.ppu.bgLayers) do
      out[#out+1]=string.format("frame=%d bg%s enabled=%s bpp8=%s tileset=0x%X tilemap=0x%X scroll=%d,%d control=0x%X",
        frame,tostring(i),tostring(b.enabled),tostring(b.bpp8Mode),b.tilesetAddr,b.tilemapAddr,b.scrollX,b.scrollY,b.control)
    end
    local f=io.open(OUT_DIR..string.format("/ppu_%d.txt",frame),"w")
    if f then f:write(table.concat(out,"\n"));f:close() end
  end
  if frame>=23601 then emu.stop(0) end
end, emu.eventType.endFrame)
