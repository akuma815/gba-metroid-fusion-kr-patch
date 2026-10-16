dofile([[G:/Downloads/Korean Traslate Project/Games/Metroid Fusion/workspace/tests/cheat_invincible.lua]])

local frames = 0
emu.addEventCallback(function()
  frames = frames + 1
  if frames >= 120 then
    emu.log("cheat invincibility + missiles smoke pass")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
