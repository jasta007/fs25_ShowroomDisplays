--[[
    SdConsole.lua
    Console commands for trying what is otherwise hard to try (open the console with the ~ key;
    the developer console must be on in game.xml):

    sdMapDisplay       the display nearest you behaves as if it came with the map, until you leave
                       the game (again to undo): machines of nobody's farm on it are locked, and a
                       turntable picks up static models standing on its disc.
    sdTestModel        puts a static copy of the machine nearest you (no wheels, no physics, like a
                       map maker's showroom model) on the turntable nearest you: with sdMapDisplay
                       on that turntable it turns with the disc.
    sdTurntables       lists the turntables: came with the map, machines held and locked, models,
                       turning, Spin speed.

    Part of Showroom Displays by Jasta007.
]]

SdConsole = {}

SdConsole.models = {}   -- loaded test models, deleted when the game ends


local function playerPosition()
    if g_localPlayer ~= nil and g_localPlayer.getPosition ~= nil then
        local x, y, z = g_localPlayer:getPosition()
        if x ~= nil then return x, y, z end
    end
    if g_currentMission ~= nil and g_currentMission.controlledVehicle ~= nil then
        return getWorldTranslation(g_currentMission.controlledVehicle.rootNode)
    end
    return nil
end


local function nearest(list, position)
    local px, _, pz = playerPosition()
    if px == nil then return nil end
    local best, bestD = nil, math.huge
    for _, item in ipairs(list) do
        local node = position(item)
        if node ~= nil and node ~= 0 then
            local x, _, z = getWorldTranslation(node)
            local d = (x - px) ^ 2 + (z - pz) ^ 2
            if d < bestD then best, bestD = item, d end
        end
    end
    return best, math.sqrt(bestD)
end


local function displays(turntablesOnly)
    local list = {}
    local system = g_currentMission ~= nil and g_currentMission.placeableSystem or nil
    for _, placeable in ipairs(system ~= nil and system.placeables or {}) do
        if SdDisplays.isDisplay(placeable) and (not turntablesOnly or SdTurntable.isTurntable(placeable.configFileName)) then
            table.insert(list, placeable)
        end
    end
    return list
end


function SdConsole:mapDisplay()
    local placeable, distance = nearest(displays(false), function(p) return p.rootNode end)
    if placeable == nil then return "No Showroom display found" end
    local on = not SdDisplays.testMapPlaced[placeable]
    SdDisplays.testMapPlaced[placeable] = on or nil
    SdDisplays.scannedAt, SdTurntable.scannedAt = nil, nil
    local entry = SdTurntable.tables[placeable.rootNode]
    if entry ~= nil then entry.propTries = 0 end
    return string.format("%s %.0f m away now %s", tostring(placeable.configFileName):match("[^/]+$") or "display",
        distance, on and "behaves as if it came with the map" or "is yours again")
end


function SdConsole:testModel()
    local turntable = nearest(displays(true), function(p) return p.rootNode end)
    if turntable == nil then return "No Showroom turntable found" end
    local vehicles = g_currentMission.vehicleSystem ~= nil and g_currentMission.vehicleSystem.vehicles or {}
    local candidates = {}
    for _, vehicle in ipairs(vehicles) do
        if vehicle.i3dFilename ~= nil and (vehicle.rootVehicle == nil or vehicle.rootVehicle == vehicle) then table.insert(candidates, vehicle) end
    end
    local vehicle = nearest(candidates, function(v) return v.rootNode end)
    if vehicle == nil then return "No machine nearby to copy" end
    local node = g_i3DManager:loadI3DFile(vehicle.i3dFilename, false, false)
    if node == nil or node == 0 then return "Could not load " .. tostring(vehicle.i3dFilename) end
    link(getRootNode(), node)
    local entry = SdTurntable.tables[turntable.rootNode]
    local disc = entry ~= nil and entry.disc or turntable.rootNode
    local x, y, z = getWorldTranslation(disc)
    setWorldTranslation(node, x, y + 0.6, z)
    setWorldRotation(node, 0, 0, 0)
    -- a showroom model's parts are static, not the dynamic parts a machine is built from
    local function makeStatic(n)
        if getRigidBodyType ~= nil and RigidBodyType ~= nil then
            local kind = getRigidBodyType(n)
            if kind ~= nil and kind ~= RigidBodyType.NONE then setRigidBodyType(n, RigidBodyType.STATIC) end
        end
        for i = 0, getNumOfChildren(n) - 1 do makeStatic(getChildAt(n, i)) end
    end
    makeStatic(node)
    table.insert(SdConsole.models, node)
    if entry ~= nil then entry.propTries = 0 end
    SdTurntable.scannedAt = nil
    return "Static copy of " .. tostring(vehicle.getName ~= nil and vehicle:getName() or vehicle.i3dFilename)
        .. " put on the turntable (use sdMapDisplay on it to make it turn)"
end


function SdConsole:turntables()
    local lines = {}
    for _, entry in pairs(SdTurntable.tables) do
        local held, locked, props = 0, 0, 0
        for _, helpers in pairs(entry.held) do
            held = held + 1
            if helpers.locked then locked = locked + 1 end
        end
        for _ in pairs(entry.props) do props = props + 1 end
        local configs = entry.placeable.configurations
        table.insert(lines, string.format("%s: map=%s held=%d locked=%d models=%d tries=%d angle=%.2f spin=%s server=%s",
            tostring(entry.placeable.configFileName):match("[^/]+$") or "?", tostring(entry.mapPlaced), held, locked, props,
            entry.propTries or 0, entry.angle or 0, tostring(configs ~= nil and configs[SdTurntable.SPEED_CONFIG] or nil),
            tostring(g_currentMission:getIsServer())))
    end
    if #lines == 0 then return "No turntables" end
    return table.concat(lines, "\n")
end


function SdConsole.install()
    if addConsoleCommand == nil then return end
    -- added with each game, taken away when it ends
    FSBaseMission.onStartMission = Utils.appendedFunction(FSBaseMission.onStartMission, function()
        addConsoleCommand("sdMapDisplay", "Showroom Displays: the display nearest you acts as if it came with the map (again to undo)", "mapDisplay", SdConsole)
        addConsoleCommand("sdTestModel", "Showroom Displays: a static copy of the machine nearest you on the turntable nearest you", "testModel", SdConsole)
        addConsoleCommand("sdTurntables", "Showroom Displays: lists the turntables and what they hold", "turntables", SdConsole)
    end)
    FSBaseMission.delete = Utils.prependedFunction(FSBaseMission.delete, function()
        for _, node in ipairs(SdConsole.models) do
            if entityExists == nil or entityExists(node) then delete(node) end
        end
        SdConsole.models = {}
        if removeConsoleCommand ~= nil then
            removeConsoleCommand("sdMapDisplay")
            removeConsoleCommand("sdTestModel")
            removeConsoleCommand("sdTurntables")
        end
    end)
end
