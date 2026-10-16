-- 초기 메뉴 흐름을 자동 입력하면서 Fusion JP 본문 폰트 ROM 읽기를 기록한다.
local OUT_DIR = "@@OUT_DIR@@"
local MAX_FRAME = @@MAX_FRAME@@
local FONT_BASE = 0x683AD8
local FONT_BASE_RUNTIME = 0x8683AD8
local FONT_END = 0x6B8000
local frame = 0
local log = {}
local cur = {}
local curN = 0

emu.addEventCallback(function()
  local buttons = {}
  for _, item in ipairs({
    {"start", 120, 127}, {"start", 300, 307},
    {"a", 520, 527}, {"a", 760, 767},
    {"a", 1000, 1007}, {"start", 1240, 1247},
    {"a", 1500, 1507}, {"a", 1760, 1767},
    {"a", 2050, 2057}, {"a", 2350, 2357},
  }) do
    if frame >= item[2] and frame <= item[3] then buttons[item[1]] = true end
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

local function put(s) log[#log + 1] = s; emu.log(s) end

emu.addMemoryCallback(function(addr, value)
  if curN < 12000 then cur[addr] = true; curN = curN + 1 end
end, emu.callbackType.read, FONT_BASE, FONT_END, nil, emu.memType.gbaPrgRom)

emu.addEventCallback(function()
  frame = frame + 1
  if curN > 0 then
    local codes = {}
    local minA, maxA = 0xFFFFFFF, 0
    for a, _ in pairs(cur) do
      if a < minA then minA = a end
      if a > maxA then maxA = a end
      local tile = math.floor((a - FONT_BASE_RUNTIME) / 32)
      local code = tile
      if (math.floor(tile / 32) % 2) == 1 then code = tile - 32 end
      codes[code] = true
    end
    local list = {}
    for c, _ in pairs(codes) do list[#list + 1] = c end
    table.sort(list)
    local parts = {}
    for i = 1, math.min(#list, 80) do parts[#parts + 1] = string.format("%04X", list[i]) end
    put(string.format("frame %d: reads=%d range=0x%06X-0x%06X codes(%d): %s",
      frame - 1, curN, minA, maxA, #list, table.concat(parts, " ")))
    cur = {}; curN = 0
  end
  if frame >= MAX_FRAME then
    local f = io.open(OUT_DIR .. "/probe_font_flow.txt", "w")
    if f then f:write(table.concat(log, "\n")); f:close() end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
