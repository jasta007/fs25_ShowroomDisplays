--[[
    SdDisplays.lua
    The display stands: where a machine stands on one (its decks), which brand it shows, and its
    colour.

    Decks are listed in each piece's own space (Driven along z):
        x, y, z   the deck's middle (y its surface there)
        hx, hz    half its size across and along
        slope     how much the surface rises for each metre of z (a display ramp)
        r         a round deck's radius instead of hx, hz (the turntable)
    A machine stands on a deck when the middle of its footprint is over it and its root is near
    the surface. Two platform display ramps facing each other, GAP apart, make a place between them.

    Boards: shapes named "eqSponsor_<n>" (and "...b" for a back face) carry a brand's logo, set
    from the game's own logo image; "eqBoardFace" shapes behind them go dark for a pale logo;
    "eqPaint" shapes take the Colour bought, or the brand's colour.
    The brand shown: another mod's choice (Realistic Equestrian's sponsor, see the API below), else
    the brand of the machine on show, else a brand picked for that spot.

    API for other mods, on g_currentMission.showroomDisplays (set at mission load):
        isDisplay(placeable)          true for one of ours
        isMapPlaced(placeable)        true for a display that came with the map
        parked(placeable)             list of vehicles on show on it
        brandOf(placeable)            the brand it shows now
        setOverride(placeable, brand, colour)   show this brand (and linear colour); nil clears

    Part of Showroom Displays by Jasta007.
]]

SdDisplays = {}

local Log = SdLog

SdDisplays.BELOW = 0.4
SdDisplays.ABOVE = 1.0
SdDisplays.GAP = { min = 2.5, max = 8.0, hx = 2.2 }
SdDisplays.RAMP = "placeables/displays/productramp.xml"
SdDisplays.SCAN_MS = 1000
SdDisplays.WAKE_RANGE = 15
SdDisplays.WAKE_MS = 2000
SdDisplays.waking = {}

-- Keep in step with the models (art/source/plinths.py in Realistic Equestrian).
SdDisplays.AREAS = {
    ["placeables/displays/drivethrough.xml"] = { { x = 0, y = 0.75, z = 0, hx = 1.6, hz = 3.0, slope = 0 } },
    ["placeables/displays/displayramp.xml"] = { { x = 0, y = 0.6, z = 0, hx = 1.5, hz = 2.0, slope = -1.2 / 4.6 } },
    ["placeables/displays/displayramplarge.xml"] = { { x = 0, y = 0.8, z = 0, hx = 1.9, hz = 3.0, slope = -1.6 / 6.6 } },
    ["placeables/displays/productramp.xml"] = { { x = 0, y = 2.0 - 3.5 * 2.0 / 7.5, z = 5.0, hx = 2.0, hz = 4.0, slope = -2.0 / 7.5 } },
    ["placeables/displays/turntable.xml"] = { { x = 0, y = 0.73, z = 0, r = 3.35, slope = 0 } },
    ["placeables/displays/turntablesmall.xml"] = { { x = 0, y = 0.58, z = 0, r = 2.3, slope = 0 } },
}

-- The Colour option: "Brand colour" first, then these (linear, as the shader takes them).
SdDisplays.COLOUR_CONFIG = "sdColour"
SdDisplays.COLOURS = {
    { "white", 0.80, 0.80, 0.78 }, { "cream", 0.72, 0.62, 0.42 }, { "red", 0.55, 0.02, 0.02 },
    { "burgundy", 0.22, 0.01, 0.02 }, { "orange", 0.80, 0.22, 0.02 }, { "yellow", 0.85, 0.60, 0.03 },
    { "lime", 0.30, 0.55, 0.04 }, { "green", 0.04, 0.30, 0.06 }, { "darkGreen", 0.01, 0.09, 0.03 },
    { "skyBlue", 0.15, 0.42, 0.75 }, { "blue", 0.02, 0.10, 0.50 }, { "navy", 0.005, 0.02, 0.10 },
    { "purple", 0.18, 0.04, 0.42 }, { "pink", 0.80, 0.22, 0.38 }, { "grey", 0.20, 0.20, 0.20 },
    { "black", 0.015, 0.015, 0.015 },
}
SdDisplays.DEFAULT_COLOUR = { 0.005, 0.02, 0.10 }   -- navy, when a brand has no colour of its own

-- The Finish option: the texture on the "stone" shapes, in option order (Plaster first).
SdDisplays.FINISH_CONFIG = "sdFinish"
SdDisplays.FINISHES = { "plinthStone_diffuse.dds", "finishWood_diffuse.dds", "finishMetal_diffuse.dds" }
SdDisplays.FINISH_DIR = "placeables/displays/"
SdDisplays.STONE = "stone"
SdDisplays.modDirectory = g_currentModDirectory

SdDisplays.LOGO = "^eqSponsor_%d+b?$"
SdDisplays.FACE = "eqBoardFace"
SdDisplays.PAINT = "eqPaint"
SdDisplays.PARAMETER = "colorScale"

SdDisplays.overrides = {}   -- placeable -> { brand, colour }
SdDisplays.state = {}       -- placeable -> { key, brand }


local function plainPath(filename)
    if type(filename) ~= "string" then return nil end
    return string.lower(string.gsub(filename, "\\", "/"))
end


--- @param filename string|nil
--- @return table|nil the decks of one of our displays
function SdDisplays.areasFor(filename)
    local path = plainPath(filename)
    if path == nil then return nil end
    for suffix, areas in pairs(SdDisplays.AREAS) do
        if string.sub(path, -#suffix) == suffix then return areas end
    end
    return nil
end


function SdDisplays.isDisplay(placeable)
    return type(placeable) == "table" and SdDisplays.areasFor(placeable.configFileName) ~= nil
end


local function isRamp(placeable)
    local path = plainPath(placeable ~= nil and placeable.configFileName or nil)
    return path ~= nil and string.sub(path, -#SdDisplays.RAMP) == SdDisplays.RAMP
end


--- @return boolean true when a machine (root at x, y, z in the display's space) stands on the deck. Pure.
function SdDisplays.inArea(area, x, y, z)
    if area.r ~= nil then
        if (x - area.x) ^ 2 + (z - area.z) ^ 2 > area.r ^ 2 then return false end
    elseif math.abs(x - area.x) > area.hx or math.abs(z - area.z) > area.hz then
        return false
    end
    local up = y - (area.y + (area.slope or 0) * (z - area.z))
    return up >= -SdDisplays.BELOW and up <= SdDisplays.ABOVE
end


--- @param a table a machine in one ramp's space { x, y, z }, b in the other's
--- @return boolean true when it stands on the ground between the two ramps' faces. Pure.
function SdDisplays.between(a, b)
    local gap = SdDisplays.GAP
    if a[3] > 0 or b[3] > 0 then return false end
    if math.abs(a[1]) > gap.hx or math.abs(b[1]) > gap.hx then return false end
    local width = -(a[3] + b[3])
    if width < gap.min or width > gap.max then return false end
    return a[2] >= -SdDisplays.BELOW and a[2] <= SdDisplays.ABOVE
end


--- @return number|nil x, y, z the middle of a vehicle's footprint, in the world
function SdDisplays.footprint(vehicle)
    local node = vehicle.rootNode
    if type(node) ~= "number" or node == 0 then return nil end
    local size = vehicle.size or {}
    return localToWorld(node, size.widthOffset or 0, 0, size.lengthOffset or 0)
end


local function vehicles()
    local system = g_currentMission ~= nil and g_currentMission.vehicleSystem or nil
    return system ~= nil and system.vehicles or {}
end


local function placeables()
    local system = g_currentMission ~= nil and g_currentMission.placeableSystem or nil
    return system ~= nil and system.placeables or {}
end


--- @param placeable table
--- @return table vehicles on show on it (on a deck, or in a gap it makes with another ramp)
function SdDisplays.parked(placeable)
    local found = {}
    local areas = SdDisplays.areasFor(placeable ~= nil and placeable.configFileName or nil)
    local root = placeable ~= nil and placeable.rootNode or nil
    if areas == nil or type(root) ~= "number" or root == 0 then return found end
    for _, vehicle in ipairs(vehicles()) do
        local wx, wy, wz = SdDisplays.footprint(vehicle)
        if wx ~= nil then
            local x, y, z = worldToLocal(root, wx, wy, wz)
            for _, area in ipairs(areas) do
                if SdDisplays.inArea(area, x, y, z) then table.insert(found, vehicle) break end
            end
        end
    end
    if #found == 0 and isRamp(placeable) then
        for _, other in ipairs(placeables()) do
            if other ~= placeable and isRamp(other) and type(other.rootNode) == "number" and other.rootNode ~= 0 then
                for _, vehicle in ipairs(vehicles()) do
                    local wx, wy, wz = SdDisplays.footprint(vehicle)
                    if wx ~= nil then
                        local a = { worldToLocal(root, wx, wy, wz) }
                        local b = { worldToLocal(other.rootNode, wx, wy, wz) }
                        if SdDisplays.between(a, b) then table.insert(found, vehicle) end
                    end
                end
            end
        end
    end
    return found
end


--- @return boolean true for a display that came with the map (not bought by a player)
function SdDisplays.isMapPlaced(placeable)
    if type(placeable) ~= "table" then return false end
    if placeable.mapBoundId ~= nil then return true end
    if placeable.isPreplaced ~= nil then return placeable.isPreplaced == true end
    return false
end


-- ---------------------------------------------------------------------------------------------
-- Look: logos, board faces and paint

local function shapesMatching(root, test)
    local found, stack = {}, { root }
    while #stack > 0 do
        local node = table.remove(stack)
        if test(getName(node) or "") then table.insert(found, node) end
        for i = 0, getNumOfChildren(node) - 1 do table.insert(stack, getChildAt(node, i)) end
    end
    return found
end


--- @param index number|nil the Finish option bought (1 = Plaster)
--- @return string the texture file it uses, inside the mod. Pure.
function SdDisplays.finishFile(index)
    local file = SdDisplays.FINISHES[type(index) == "number" and index or 1] or SdDisplays.FINISHES[1]
    return SdDisplays.FINISH_DIR .. file
end


local function showFinish(node, path)
    if setMaterialDiffuseMapFromFile == nil then return end
    local material = getMaterial(node, 0)
    if material == nil or material == 0 then return end
    local finished = setMaterialDiffuseMapFromFile(material, path, true, true, false)
    if finished ~= nil and finished ~= 0 then setMaterial(node, finished, 0) end
end


local function showLogo(node, brand)
    if brand == nil or setMaterialDiffuseMapFromFile == nil then return false end
    local material = getMaterial(node, 0)
    if material == nil or material == 0 then return false end
    local logo = setMaterialDiffuseMapFromFile(material, brand.image, true, true, false)
    if logo == nil or logo == 0 then return false end
    setMaterial(node, logo, 0)
    return true
end


local function paint(nodes, colour)
    if colour == nil or setShaderParameter == nil then return end
    for _, node in ipairs(nodes) do
        if getHasShaderParameter == nil or getHasShaderParameter(node, SdDisplays.PARAMETER) then
            setShaderParameter(node, SdDisplays.PARAMETER, colour[1], colour[2], colour[3], 0, false)
        end
    end
end


--- @param index number|nil the Colour option bought (1 = Brand colour)
--- @return table|nil the colour it picks, nil for Brand colour. Pure.
function SdDisplays.optionColour(index)
    if type(index) ~= "number" or index <= 1 then return nil end
    local entry = SdDisplays.COLOURS[index - 1]
    return entry ~= nil and { entry[2], entry[3], entry[4] } or nil
end


--- @param placeable table
--- @return string|nil the brand the display shows
function SdDisplays.brandOf(placeable)
    local override = SdDisplays.overrides[placeable]
    if override ~= nil and override.brand ~= nil then return override.brand end
    for _, vehicle in ipairs(SdDisplays.parked(placeable)) do
        local brand = SdBrands.of(vehicle)
        if brand ~= nil then return brand end
    end
    local _, names = SdBrands.all()
    local x, _, z = getWorldTranslation(placeable.rootNode)
    return SdBrands.pick(names, x, z)
end


--- Set a display's logos and colours (only when what it should show has changed).
function SdDisplays.apply(placeable)
    if not SdDisplays.isDisplay(placeable) or type(placeable.rootNode) ~= "number" or placeable.rootNode == 0 then return end
    local brand = SdDisplays.brandOf(placeable)
    local override = SdDisplays.overrides[placeable]
    local option = placeable.configurations ~= nil and placeable.configurations[SdDisplays.COLOUR_CONFIG] or nil
    local finish = placeable.configurations ~= nil and placeable.configurations[SdDisplays.FINISH_CONFIG] or nil
    local key = tostring(brand) .. "|" .. tostring(option) .. "|" .. tostring(override ~= nil and override.colour or nil)
        .. "|" .. tostring(finish)
    local state = SdDisplays.state[placeable]
    if state ~= nil and state.key == key then return end
    local previous = SdDisplays.state[placeable]
    SdDisplays.state[placeable] = { key = key, brand = brand, finish = finish }
    local byName = SdBrands.all()
    local root = placeable.rootNode
    -- the finish only when it changes (Plaster is what the model has)
    if (previous == nil and (finish or 1) ~= 1) or (previous ~= nil and previous.finish ~= finish) then
        local path = (SdDisplays.modDirectory or "") .. SdDisplays.finishFile(finish)
        for _, node in ipairs(shapesMatching(root, function(name) return name == SdDisplays.STONE end)) do
            SdLog.try("finish", showFinish, node, path)
        end
    end
    if byName[brand or ""] ~= nil then
        for _, node in ipairs(shapesMatching(root, function(name) return string.match(name, SdDisplays.LOGO) ~= nil end)) do
            SdLog.try("logo", showLogo, node, byName[brand])
        end
    end
    paint(shapesMatching(root, function(name) return name == SdDisplays.FACE end), SdBrands.faceColour(brand))
    local colour = override ~= nil and override.colour or SdDisplays.optionColour(option)
    if colour == nil then colour = SdBrands.colour(brand) or SdDisplays.DEFAULT_COLOUR end
    paint(shapesMatching(root, function(name) return name == SdDisplays.PAINT end), colour)
end


--- Another mod (Realistic Equestrian) shows its own brand and colour on a display.
--- @param placeable table
--- @param brand string|nil nil gives the display its own choice back
--- @param colour table|nil linear { r, g, b }
function SdDisplays.setOverride(placeable, brand, colour)
    if type(placeable) ~= "table" then return end
    if brand == nil and colour == nil then
        SdDisplays.overrides[placeable] = nil
    else
        SdDisplays.overrides[placeable] = { brand = brand, colour = colour }
    end
    SdLog.try("display look", SdDisplays.apply, placeable)
end


-- ---------------------------------------------------------------------------------------------
-- Colour option

function SdDisplays.registerConfiguration()
    local manager = g_placeableConfigurationManager
    if manager == nil or manager.addConfigurationType == nil or PlaceableConfigurationItem == nil then
        Log:warning("no placeable configurations; displays keep their colour")
        return
    end
    for _, entry in ipairs({ { SdDisplays.COLOUR_CONFIG, "sd_config_colour", "Colour" },
                             { SdDisplays.FINISH_CONFIG, "sd_config_finish", "Finish" } }) do
        local name, textKey, title = entry[1], entry[2], entry[3]
        if manager.configurations == nil or manager.configurations[name] == nil then
            if g_i18n ~= nil and g_i18n:hasText(textKey) then title = g_i18n:getText(textKey) end
            manager:addConfigurationType(name, title, name, PlaceableConfigurationItem)
        end
    end
end


-- ---------------------------------------------------------------------------------------------
-- Each frame

--- Wake machines near a display that goes, so they drop instead of floating where it stood.
function SdDisplays.wakeNear(placeable)
    if type(placeable.rootNode) ~= "number" or placeable.rootNode == 0 then return end
    local px, _, pz = getWorldTranslation(placeable.rootNode)
    local untilAt = (g_time or 0) + SdDisplays.WAKE_MS
    for _, vehicle in ipairs(vehicles()) do
        if type(vehicle.rootNode) == "number" and vehicle.rootNode ~= 0 then
            local vx, _, vz = getWorldTranslation(vehicle.rootNode)
            if (vx - px) ^ 2 + (vz - pz) ^ 2 <= SdDisplays.WAKE_RANGE ^ 2 then SdDisplays.waking[vehicle] = untilAt end
        end
    end
end


local function wake(vehicle)
    if vehicle.isDeleted or vehicle.isDeleting then return end
    for _, component in ipairs(vehicle.components or {}) do
        local node = component.node
        if type(node) == "number" and node ~= 0 and (entityExists == nil or entityExists(node)) then
            if I3DUtil ~= nil and I3DUtil.wakeUpObject ~= nil then
                I3DUtil.wakeUpObject(node)
            elseif getLinearVelocity ~= nil and setLinearVelocity ~= nil then
                local vx, vy, vz = getLinearVelocity(node)
                setLinearVelocity(node, vx or 0, vy or 0, vz or 0)
            end
        end
    end
    if vehicle.raiseActive ~= nil then vehicle:raiseActive() end
end


function SdDisplays.update()
    local now = g_time or 0
    if g_currentMission ~= nil and g_currentMission.showroomDisplays == nil then g_currentMission.showroomDisplays = SdDisplays.api end
    if next(SdDisplays.waking) ~= nil then
        for vehicle, untilAt in pairs(SdDisplays.waking) do
            if now > untilAt or vehicle.isDeleted then SdDisplays.waking[vehicle] = nil else wake(vehicle) end
        end
    end
    if SdDisplays.scannedAt ~= nil and now - SdDisplays.scannedAt < SdDisplays.SCAN_MS and now >= SdDisplays.scannedAt then return end
    SdDisplays.scannedAt = now
    local seen = {}
    for _, placeable in ipairs(placeables()) do
        if SdDisplays.isDisplay(placeable) then
            seen[placeable] = true
            SdLog.try("display look", SdDisplays.apply, placeable)
        end
    end
    -- the shop's preview while placing one
    local gui = g_gui ~= nil and g_gui.currentGui or nil
    local target = gui ~= nil and gui.target or nil
    local brush = type(target) == "table" and target.brush or nil
    if type(brush) == "table" and SdDisplays.isDisplay(brush.placeable) then
        seen[brush.placeable] = true
        SdLog.try("display preview", SdDisplays.apply, brush.placeable)
    end
    for placeable in pairs(SdDisplays.state) do
        if not seen[placeable] then SdDisplays.state[placeable] = nil end
    end
    for placeable in pairs(SdDisplays.overrides) do
        if not seen[placeable] then SdDisplays.overrides[placeable] = nil end
    end
end


SdDisplays.api = {
    isDisplay = function(p) return SdDisplays.isDisplay(p) end,
    isMapPlaced = function(p) return SdDisplays.isMapPlaced(p) end,
    parked = function(p) return SdDisplays.parked(p) end,
    brandOf = function(p) return SdDisplays.brandOf(p) end,
    setOverride = function(p, brand, colour) SdDisplays.setOverride(p, brand, colour) end,
    areasFor = function(filename) return SdDisplays.areasFor(filename) end,
}


function SdDisplays.install()
    SdLog.try("colour and finish options", SdDisplays.registerConfiguration)
    -- paint as the Colour option loads, in the shop's preview too
    if PlaceableConfigurationItem ~= nil and PlaceableConfigurationItem.onPostLoad ~= nil then
        PlaceableConfigurationItem.onPostLoad = Utils.appendedFunction(PlaceableConfigurationItem.onPostLoad, function(item, placeable)
            if type(item) == "table" and (item.configName == SdDisplays.COLOUR_CONFIG or item.configName == SdDisplays.FINISH_CONFIG)
                and SdDisplays.isDisplay(placeable) then
                -- keep the finish we know about; only the cache key is reset
                if SdDisplays.state[placeable] ~= nil then SdDisplays.state[placeable].key = nil end
                SdLog.try("display look", SdDisplays.apply, placeable)
            end
        end)
    end
    if Placeable ~= nil and Placeable.delete ~= nil then
        Placeable.delete = Utils.prependedFunction(Placeable.delete, function(placeable)
            if SdDisplays.isDisplay(placeable) then
                SdLog.try("display wake", SdDisplays.wakeNear, placeable)
                SdDisplays.state[placeable], SdDisplays.overrides[placeable] = nil, nil
            end
        end)
    end
    FSBaseMission.onStartMission = Utils.appendedFunction(FSBaseMission.onStartMission, function(mission)
        mission.showroomDisplays = SdDisplays.api
    end)
    FSBaseMission.update = Utils.appendedFunction(FSBaseMission.update, function()
        SdLog.try("displays", SdDisplays.update)
    end)
    FSBaseMission.delete = Utils.prependedFunction(FSBaseMission.delete, function()
        SdDisplays.state, SdDisplays.overrides, SdDisplays.waking, SdDisplays.scannedAt = {}, {}, {}, nil
    end)
end
