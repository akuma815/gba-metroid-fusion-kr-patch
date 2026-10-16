-- Trace saved-slot difficulty/location strings while showing file select.
local OUT_DIR = "@@OUT_DIR@@"
local SHOTS = @@SHOTS@@
local frame = 0
local shot_index = 1
local lines = {}
local seen = {}

local function hit(tag)
  return function(address, value)
    if frame > 3950 then return end
    local key = string.format("%s:%08X", tag, address)
    if not seen[key] then
      seen[key] = true
      lines[#lines + 1] = string.format(
        "frame=%d tag=%s rom=0x%06X value=0x%02X",
        frame, tag, address, value)
    end
  end
end

for _, item in ipairs({
  {"location_ja_original", 0x6B153E, 0x6B156F},
  {"location_hira_original", 0x6B2466, 0x6B2497},
  {"location_ko_relocated", 0x6C0F4E, 0x6C0F6F},
  {"difficulty_summary", 0x7469D4, 0x746A0F},
  {"file_select_tables", 0x7F1118, 0x7F11FF},
}) do
  emu.addMemoryCallback(hit(item[1]), emu.callbackType.read,
    item[2], item[3], nil, emu.memType.gbaPrgRom)
end

local function held(first, last) return frame >= first and frame <= last end
emu.addEventCallback(function()
  local buttons = {}
  if held(3520,3527) or held(3720,3727) then buttons.start=true end
  emu.setInput(buttons,0)
end, emu.eventType.inputPolled)

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
  if frame >= 3950 then
    table.sort(lines)
    local f = io.open(OUT_DIR .. "/saved_file_select_reads.txt", "w")
    if f then f:write(table.concat(lines, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
