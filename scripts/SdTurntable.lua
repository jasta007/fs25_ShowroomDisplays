--[[
    SdTurntable.lua
    The turntable: its disc ("eqTurntableDisc") turns slowly, and a machine left on it turns with it.

    Turning a machine with real physics would fight the wheels, so, like a ferry carrying a
    vehicle, the machine is held instead: once it has stood on the disc with nobody in it for
    HOLD_MS, it slides to the disc's middle, comes out of the physics and follows the disc (each
    of its parts copies a helper node linked under the disc). Getting in, hitching anything to it,
    selling it or the turntable, or leaving the game gives it back its physics where it is.

    A machine is held with everything hitched to it (a wheel loader's bucket too). One towing a
    trailer isn't held, so a long trailer doesn't swing round. The disc stands still when empty.
    Spin speed (bought or changed later): Off, Slow (a turn in 2 minutes), Medium (1), Fast (40 s);
    Off still holds the machine. In multiplayer nothing is held yet.

    Part of Showroom Displays by Jasta007.
]]

SdTurntable = {}

local Log = SdLog

SdTurntable.XML = "placeables/displays/turntable.xml"
SdTurntable.DISC = "eqTurntableDisc"
SdTurntable.SPEED_CONFIG = "sdSpin"
-- ms per turn for each Spin speed option, in order: Off, Slow, Medium, Fast
SdTurntable.TURN_MS = { 0, 120000, 60000, 40000 }
SdTurntable.DEFAULT_SPEED = 2
SdTurntable.HOLD_MS = 3000
SdTurntable.STILL_KMH = 0.5
SdTurntable.SCAN_MS = 2000

SdTurntable.tables = {}
SdTurntable.scannedAt = nil


function SdTurntable.isTurntable(filename)
    if type(filename) ~= "string" then return false end
    local path = string.lower(string.gsub(filename, "\\", "/"))
    return string.sub(path, -#SdTurntable.XML) == SdTurntable.XML
end


--- @param index number|nil the Spin speed option
--- @return number ms per turn, 0 for Off. Pure.
function SdTurntable.turnMs(index)
    return SdTurntable.TURN_MS[index or SdTurntable.DEFAULT_SPEED] or SdTurntable.TURN_MS[SdTurntable.DEFAULT_SPEED]
end


--- @return number the disc's turn after dt ms, kept within one full turn. Pure.
function SdTurntable.advance(angle, dt, turnMs)
    if (turnMs or 0) <= 0 then return angle end
    local turn = 2 * math.pi
    return (angle + turn * (dt or 0) / turnMs) % turn
end


local function inUse(vehicle)
    if vehicle.getIsControlled ~= nil and vehicle:getIsControlled() then return true end
    if vehicle.getIsEntered ~= nil and vehicle:getIsEntered() then return true end
    if vehicle.getIsAIActive ~= nil and vehicle:getIsAIActive() then return true end
    return false
end


local function chain(vehicle)
    local root = vehicle.rootVehicle or vehicle
    local list = { root }
    if root.getChildVehicles ~= nil then
        for _, child in pairs(root:getChildVehicles() or {}) do
            if child ~= root then table.insert(list, child) end
        end
    end
    return list
end


function SdTurntable.isTrailerJoint(jointType)
    local names = AttacherJoints ~= nil and AttacherJoints.jointTypeNameToInt or nil
    if jointType == nil or names == nil then return false end
    for name, value in pairs(names) do
        if value == jointType then return string.find(string.lower(name), "trailer", 1, true) ~= nil end
    end
    return false
end


local function towsTrailer(machines)
    for _, machine in ipairs(machines) do
        if machine.getAttachedImplements ~= nil then
            local joints = machine.getAttacherJoints ~= nil and machine:getAttacherJoints() or nil
            for _, implement in pairs(machine:getAttachedImplements() or {}) do
                local joint = joints ~= nil and implement.jointDescIndex ~= nil and joints[implement.jointDescIndex] or nil
                if joint ~= nil and SdTurntable.isTrailerJoint(joint.jointType) then return true end
            end
        end
    end
    return false
end


local function isHead(vehicle)
    return vehicle.rootVehicle == nil or vehicle.rootVehicle == vehicle
end


local function still(vehicle)
    local speed = vehicle.getLastSpeed ~= nil and vehicle:getLastSpeed() or 0
    return math.abs(speed) < SdTurntable.STILL_KMH
end


local function exists(vehicle)
    if vehicle.isDeleted or vehicle.isDeleting then return false end
    return type(vehicle.rootNode) == "number" and (entityExists == nil or entityExists(vehicle.rootNode))
end


local function onDisc(entry, vehicle)
    local areas = SdDisplays.areasFor(SdTurntable.XML)
    local wx, wy, wz = SdDisplays.footprint(vehicle)
    if areas == nil or wx == nil then return false end
    local x, y, z = worldToLocal(entry.placeable.rootNode, wx, wy, wz)
    return SdDisplays.inArea(areas[1], x, y, z)
end


local function hold(entry, vehicle)
    local machines = chain(vehicle)
    for _, machine in ipairs(machines) do
        if machine.removeFromPhysics == nil or #(machine.components or {}) == 0 then return end
    end
    local fx, _, fz = SdDisplays.footprint(vehicle)
    local cx, _, cz = getWorldTranslation(entry.disc)
    local dx, dz = cx - fx, cz - fz
    local components = {}
    for _, machine in ipairs(machines) do
        machine:removeFromPhysics()
        for _, component in ipairs(machine.components) do table.insert(components, component) end
    end
    local helpers = { machines = machines }
    for _, component in ipairs(components) do
        local node = component.node
        local x, y, z = getWorldTranslation(node)
        setWorldTranslation(node, x + dx, y, z + dz)
        local helper = createTransformGroup("sdTurntableHold")
        link(entry.disc, helper)
        setWorldTranslation(helper, x + dx, y, z + dz)
        setWorldQuaternion(helper, getWorldQuaternion(node))
        table.insert(helpers, { node = node, helper = helper })
    end
    entry.held[vehicle] = helpers
end


local function release(entry, vehicle)
    local helpers = entry.held[vehicle]
    entry.held[vehicle] = nil
    if helpers == nil then return end
    for _, h in ipairs(helpers) do
        if entityExists == nil or entityExists(h.helper) then delete(h.helper) end
    end
    for _, machine in ipairs(helpers.machines or { vehicle }) do
        if exists(machine) and machine.addToPhysics ~= nil then machine:addToPhysics() end
    end
end


local function follow(entry)
    for _, helpers in pairs(entry.held) do
        for _, h in ipairs(helpers) do
            if entityExists == nil or (entityExists(h.node) and entityExists(h.helper)) then
                setWorldTranslation(h.node, getWorldTranslation(h.helper))
                setWorldQuaternion(h.node, getWorldQuaternion(h.helper))
            end
        end
    end
end


local function isMultiplayer()
    local info = g_currentMission ~= nil and g_currentMission.missionDynamicInfo or nil
    return info ~= nil and info.isMultiplayer == true
end


function SdTurntable.findDisc(node)
    local stack = { node }
    while #stack > 0 do
        local current = table.remove(stack)
        if getName(current) == SdTurntable.DISC then return current end
        for i = 0, getNumOfChildren(current) - 1 do table.insert(stack, getChildAt(current, i)) end
    end
    return nil
end


local function scan(now)
    local seen = {}
    local system = g_currentMission ~= nil and g_currentMission.placeableSystem or nil
    for _, placeable in ipairs(system ~= nil and system.placeables or {}) do
        local root = placeable.rootNode
        if SdTurntable.isTurntable(placeable.configFileName) and type(root) == "number" and root ~= 0 then
            seen[root] = true
            if SdTurntable.tables[root] == nil then
                local disc = SdTurntable.findDisc(root)
                if disc ~= nil then
                    SdTurntable.tables[root] = { placeable = placeable, disc = disc, angle = 0, held = {}, waiting = {} }
                end
            end
        end
    end
    for root, entry in pairs(SdTurntable.tables) do
        if not seen[root] then
            for vehicle in pairs(entry.held) do release(entry, vehicle) end
            SdTurntable.tables[root] = nil
        end
    end
    SdTurntable.scannedAt = now
end


function SdTurntable.update(dt)
    local now = g_time or 0
    if SdTurntable.scannedAt == nil or now - SdTurntable.scannedAt >= SdTurntable.SCAN_MS or now < SdTurntable.scannedAt then
        scan(now)
    end
    if next(SdTurntable.tables) == nil then return end
    local holding = not isMultiplayer() and g_currentMission ~= nil and g_currentMission.vehicleSystem ~= nil
    for _, entry in pairs(SdTurntable.tables) do
        local configs = entry.placeable.configurations
        local turnMs = SdTurntable.turnMs(configs ~= nil and configs[SdTurntable.SPEED_CONFIG] or nil)
        if next(entry.held) ~= nil and turnMs > 0 then
            entry.angle = SdTurntable.advance(entry.angle, dt, turnMs)
            setRotation(entry.disc, 0, entry.angle, 0)
        end
        if holding then
            for vehicle, helpers in pairs(entry.held) do
                local now_ = chain(vehicle)
                local changed = #now_ ~= #(helpers.machines or {})
                for _, machine in ipairs(now_) do
                    if not exists(machine) or inUse(machine) then changed = true end
                end
                if not exists(vehicle) or changed then release(entry, vehicle) end
            end
            follow(entry)
            if now - (entry.checkedAt or 0) >= 250 or now < (entry.checkedAt or 0) then
                local elapsed = now - (entry.checkedAt or now)
                entry.checkedAt = now
                local waiting = {}
                for _, vehicle in ipairs(g_currentMission.vehicleSystem.vehicles or {}) do
                    local free = isHead(vehicle) and entry.held[vehicle] == nil and exists(vehicle) and onDisc(entry, vehicle)
                    if free then
                        local machines = chain(vehicle)
                        for _, machine in ipairs(machines) do
                            if inUse(machine) or not still(machine) then free = false end
                        end
                        local ok, tows = SdLog.try("turntable trailer", towsTrailer, machines)
                        if free and ok and tows then free = false end
                    end
                    if free then
                        local waited = (entry.waiting[vehicle] or 0) + math.max(0, elapsed)
                        if waited >= SdTurntable.HOLD_MS then
                            SdLog.try("turntable hold", hold, entry, vehicle)
                        else
                            waiting[vehicle] = waited
                        end
                    end
                end
                entry.waiting = waiting
            end
        end
    end
end


function SdTurntable.releaseAll()
    for _, entry in pairs(SdTurntable.tables) do
        for vehicle in pairs(entry.held) do release(entry, vehicle) end
    end
end


function SdTurntable.registerConfiguration()
    local manager = g_placeableConfigurationManager
    if manager == nil or manager.addConfigurationType == nil or PlaceableConfigurationItem == nil then return end
    if manager.configurations == nil or manager.configurations[SdTurntable.SPEED_CONFIG] == nil then
        local title = "Spin speed"
        if g_i18n ~= nil and g_i18n:hasText("sd_config_spin") then title = g_i18n:getText("sd_config_spin") end
        manager:addConfigurationType(SdTurntable.SPEED_CONFIG, title, SdTurntable.SPEED_CONFIG, PlaceableConfigurationItem)
    end
end


function SdTurntable.install()
    SdLog.try("spin speed option", SdTurntable.registerConfiguration)
    FSBaseMission.update = Utils.appendedFunction(FSBaseMission.update, function(_, dt)
        SdLog.try("turntable", SdTurntable.update, dt)
    end)
    -- before saving, machines go back into the physics where they stand, so they save there
    if FSBaseMission.saveSavegame ~= nil then
        FSBaseMission.saveSavegame = Utils.prependedFunction(FSBaseMission.saveSavegame, function()
            SdLog.try("turntable release", SdTurntable.releaseAll)
        end)
    end
    FSBaseMission.delete = Utils.prependedFunction(FSBaseMission.delete, function()
        SdLog.try("turntable release", SdTurntable.releaseAll)
        SdTurntable.tables, SdTurntable.scannedAt = {}, nil
    end)
end
