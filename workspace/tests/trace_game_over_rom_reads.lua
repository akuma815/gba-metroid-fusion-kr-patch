-- Trace ROM reads during Game Over initialization from a gameplay savestate.
local OUT_DIR = "@@OUT_DIR@@"
local STATE_PATH = "@@STATE_PATH@@"
local frame = 0
local loaded = false
local killed = false
local blocks = {}
local load_callback

load_callback = emu.addMemoryCallback(function()
  if loaded then return end
  local file = assert(io.open(STATE_PATH, "rb"))
  local state = file:read("*all")
  file:close()
  emu.loadSavestate(state)
  loaded = true
  emu.removeMemoryCallback(load_callback)
end, emu.callbackType.exec, 0x08000000, 0x09FFFFFF,
    emu.cpuType.gba, emu.memType.gbaMemory)

emu.addMemoryCallback(function(address)
  if loaded and killed then
    local normalized = address
    if normalized < 0x08000000 then normalized = normalized + 0x08000000 end
    blocks[math.floor(normalized / 32) * 32] = true
  end
end, emu.callbackType.read, 0x08700000, 0x087FFFFF,
    emu.cpuType.gba, emu.memType.gbaMemory)

emu.addEventCallback(function()
  frame = frame + 1
  if loaded and frame == 10 and not killed then
    emu.write(0x1344, 0, emu.memType.gbaIntWorkRam)
    emu.write(0x1345, 0, emu.memType.gbaIntWorkRam)
    killed = true
  end
  if loaded and frame == 400 then
    local addresses = {}
    for address in pairs(blocks) do addresses[#addresses + 1] = address end
    table.sort(addresses)
    local file = assert(io.open(OUT_DIR .. "/rom_read_blocks.txt", "w"))
    for _, address in ipairs(addresses) do file:write(string.format("0x%08X\n", address)) end
    file:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
