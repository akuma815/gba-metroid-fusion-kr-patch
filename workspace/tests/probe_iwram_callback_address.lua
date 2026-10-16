local OUT_DIR = "@@OUT_DIR@@"
local lines = {}

local function hit(tag)
  return function(address, value)
    lines[#lines + 1] = string.format("%s address=0x%08X value=0x%02X", tag, address, value)
  end
end

emu.addMemoryCallback(hit("offset"), emu.callbackType.write, 0xEA4, 0xEEB, nil, emu.memType.gbaIntWorkRam)
emu.addMemoryCallback(hit("cpu"), emu.callbackType.write, 0x03000EA4, 0x03000EEB, nil, emu.memType.gbaIntWorkRam)

local frame = 0
emu.addEventCallback(function()
  frame = frame + 1
  if frame == 5 then
    emu.write(0xEA4, 0x5A, emu.memType.gbaIntWorkRam)
  elseif frame == 10 then
    local f = io.open(OUT_DIR .. "/iwram_callback_address.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
