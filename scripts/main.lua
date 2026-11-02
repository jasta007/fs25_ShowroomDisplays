--[[
    main.lua
    Showroom Displays: display stands for machines. Sources the scripts and installs the hooks.
    Needs no other mod; Realistic Equestrian uses g_currentMission.showroomDisplays when present.

    Part of Showroom Displays by Jasta007.
]]

local modDirectory = g_currentModDirectory

source(modDirectory .. "scripts/SdLog.lua")
source(modDirectory .. "scripts/SdBrands.lua")
source(modDirectory .. "scripts/SdDisplays.lua")
source(modDirectory .. "scripts/SdTurntable.lua")
source(modDirectory .. "scripts/SdTurntableEvent.lua")
source(modDirectory .. "scripts/SdConsole.lua")

SdDisplays.install()
SdTurntable.install()
SdConsole.install()
SdLog:info("Showroom Displays by Jasta007 active")
