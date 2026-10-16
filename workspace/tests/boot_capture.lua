-- Mesen 2 testRunner: GBA 화면 기준선 캡처
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local idx = 1

local function save(name)
  local png = emu.takeScreenshot()
  local path = OUT_DIR .. "/" .. name .. ".png"
  local f = io.open(path, "wb")
  if f then
    f:write(png)
    f:close()
    emu.log("saved " .. path)
  else
    emu.log("FAILED to open " .. path)
  end
end

emu.addEventCallback(function()
  frame = frame + 1
  while idx <= #SHOTS and SHOTS[idx].frame <= frame do
    save(string.format("%05d_%s", SHOTS[idx].frame, SHOTS[idx].name))
    idx = idx + 1
  end
  if idx > #SHOTS then
    emu.log("done at frame " .. frame)
    emu.stop(0)
  end
end, emu.eventType.endFrame)

emu.log("boot_capture started")
