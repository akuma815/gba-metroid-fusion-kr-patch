-- True clean boot; stop input and capture when message/ja/043 is read.
local OUT_DIR = "@@OUT_DIR@@"
local frame = 0
local trigger_frame = nil
local saved = false

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

local function save(name)
  local png = emu.takeScreenshot()
  local file = io.open(OUT_DIR .. "/" .. name .. ".png", "wb")
  if file then file:write(png); file:close() end
end

emu.addEventCallback(function()
  frame = frame + 1
  if trigger_frame and not saved and frame >= trigger_frame + 160 then
    save(string.format("%05d_message_043", frame))
    saved = true
  end
  if (saved and frame >= trigger_frame + 220) or frame >= 24000 then
    local file = io.open(OUT_DIR .. "/trigger.txt", "w")
    if file then file:write("trigger_frame=" .. tostring(trigger_frame)); file:close() end
    emu.stop(trigger_frame and 0 or 1)
  end
end, emu.eventType.endFrame)
