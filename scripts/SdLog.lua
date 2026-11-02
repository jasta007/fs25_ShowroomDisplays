--[[
    SdLog.lua
    Logging, and the mod's one pcall: every protected call goes through SdLog.try, so a caught
    error is always logged (GIANTS' TestRunner flags a bare pcall). Each context logs its first
    failure in full, then only every 1000th, since some run every frame.

    Part of Showroom Displays by Jasta007.
]]

SdLog = {}

SdLog.NAME = "ShowroomDisplays"

local function emit(prefix, fmt, ...)
    print(string.format("%s[%s] %s", prefix, SdLog.NAME, string.format(fmt, ...)))
end

function SdLog:error(fmt, ...) emit("Error: ", fmt, ...) end
function SdLog:warning(fmt, ...) emit("Warning: ", fmt, ...) end
function SdLog:info(fmt, ...) emit("Info: ", fmt, ...) end

local failures = {}

local function protected(fn, ...)
    return pcall(fn, ...)
end

local function finish(context, ok, ...)
    if not ok then
        local count = (failures[context] or 0) + 1
        failures[context] = count
        if count == 1 then
            SdLog:warning("%s failed: %s", context, tostring((...)))
        elseif count % 1000 == 0 then
            SdLog:warning("%s has failed %d times", context, count)
        end
    end
    return ok, ...
end

--- Call fn(...), logging a failure instead of raising it.
--- @param context string
--- @return boolean ok, ... fn's results, as pcall gives them
function SdLog.try(context, fn, ...)
    return finish(context, protected(fn, ...))
end
