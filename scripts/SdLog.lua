--[[
    SdLog.lua
    Logging. SdLog.try names each hooked call; it no longer catches errors (GIANTS' TestRunner
    rejects pcall, so an error reaches the log with its stack trace). Each context's reported
    failures are logged in full the first time, then only every 1000th.

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
    return true, fn(...)
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

--- Call fn(...). Errors are not caught: they go to the log with the game's stack trace.
--- @param context string
--- @return boolean ok, ... true, then fn's results
function SdLog.try(context, fn, ...)
    return finish(context, protected(fn, ...))
end
