-- Metroid Fusion (Japan) Korean QA: invincibility + unlimited missiles for Mesen 2.
--
-- Verified target (METROID4JPN / AMTJ):
--   IWRAM 0x03001344 = current energy (u16)
--   IWRAM 0x03001346 = maximum energy (u16)
--   IWRAM 0x03001348 = current missiles (u16)
--   IWRAM 0x0300134A = maximum missiles (u16)
-- Mesen's gbaIntWorkRam memory type uses the relative offset, hence 0x1344.
--
-- The callback runs before a write. Once normal gameplay energy has remained
-- valid for 60 frames, writes to the two current-energy bytes are replaced by
-- cached bytes from the last valid energy value. The callback's address can be
-- reported as a CPU address even though the registered range is IWRAM-relative;
-- reading that address back as an IWRAM offset returns zero and causes instant
-- death. Never use the callback address directly for an IWRAM read here.
-- Damage cannot reduce energy. Once missiles have been acquired and their
-- current/maximum pair is stable, writes that would change the current missile
-- count are replaced with the cached maximum count. Maximum missiles, item
-- acquisition, the ROM, saves and translation data remain untouched.
-- Scripted attacks can still play their knockback/hurt animation.
--
-- Mesen: Debug -> Script Window -> open this file -> Run (F5).
-- Stop it by closing/stopping the Script Window.

local ENERGY = 0x1344
local MAX_ENERGY = 0x1346
local MISSILES = 0x1348
local MAX_MISSILES = 0x134A
local IW = emu.memType.gbaIntWorkRam

local stable = 0
local armed = false
local blockedWrites = 0
local protectedEnergy = 0
local missileStable = 0
local missileArmed = false
local blockedMissileWrites = 0
local protectedMissiles = 0

local function r16(address)
  return emu.read(address, IW, false) + emu.read(address + 1, IW, false) * 256
end

emu.addEventCallback(function()
  local current = r16(ENERGY)
  local maximum = r16(MAX_ENERGY)
  if current >= 1 and current <= 1299 and maximum >= current and maximum <= 1299 then
    stable = stable + 1
    if stable >= 60 and not armed then
      armed = true
      protectedEnergy = current
      emu.log(string.format("Fusion JP QA invincibility enabled: energy=%d/%d", current, maximum))
    end
  else
    stable = 0
    armed = false
  end

  local currentMissiles = r16(MISSILES)
  local maximumMissiles = r16(MAX_MISSILES)
  if armed and maximumMissiles >= 1 and maximumMissiles <= 999
      and currentMissiles >= 1 and currentMissiles <= maximumMissiles then
    missileStable = missileStable + 1
    protectedMissiles = maximumMissiles
    if missileStable >= 60 and not missileArmed then
      missileArmed = true
      emu.log(string.format(
        "Fusion JP QA unlimited missiles enabled: missiles=%d/%d",
        currentMissiles, maximumMissiles
      ))
    end
  else
    missileStable = 0
    missileArmed = false
    protectedMissiles = 0
  end
end, emu.eventType.endFrame)

emu.addMemoryCallback(function(address, value)
  if armed then
    blockedWrites = blockedWrites + 1
    local offset = address % 0x10000
    if offset == ENERGY then return protectedEnergy % 256 end
    if offset == ENERGY + 1 then return math.floor(protectedEnergy / 256) end
  end
  return value
end, emu.callbackType.write, ENERGY, ENERGY + 1, nil, IW)

emu.addMemoryCallback(function(address, value)
  if missileArmed then
    blockedMissileWrites = blockedMissileWrites + 1
    local offset = address % 0x10000
    if offset == MISSILES then return protectedMissiles % 256 end
    if offset == MISSILES + 1 then return math.floor(protectedMissiles / 256) end
  end
  return value
end, emu.callbackType.write, MISSILES, MISSILES + 1, nil, IW)

emu.addEventCallback(function()
  if armed then
    local missileStatus = missileArmed and string.format(" M%d", protectedMissiles) or " M--"
    emu.drawString(
      130, 2,
      string.format("QA INV %d%s", blockedWrites, missileStatus),
      0xFFFF60, 0x000000
    )
  end
end, emu.eventType.startFrame)

emu.log("Fusion JP QA invincibility + unlimited missiles loaded; waiting for valid gameplay state")
