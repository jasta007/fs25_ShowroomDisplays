--[[
    SdBrands.lua
    The game's brands as a display shows them: the logo image, the brand's colour, and the board
    colour behind the logo (dark behind a white or pale logo, which would vanish on a white board).
    Brand names, logos and colours are read from the game at run time; none are shipped.

    Part of Showroom Displays by Jasta007.
]]

SdBrands = {}

local Log = SdLog

-- Brands whose colour is fixed here whatever the game's paints say (Lizard's paint is red, its logo green).
SdBrands.OWN_COLOURS = {
    LIZARD = { 132, 189, 41 },
}

-- Brands' main colours, used before the game's paints: sRGB 0-255.
SdBrands.COLOURS = {
    FENDT = { 62, 122, 39 }, MASSEYFERGUSON = { 190, 22, 34 }, JOHNDEERE = { 54, 124, 43 },
    CASEIH = { 181, 18, 27 }, NEWHOLLAND = { 13, 77, 161 }, CLAAS = { 180, 198, 24 },
    DEUTZFAHR = { 108, 179, 63 }, VALTRA = { 200, 16, 46 }, KUBOTA = { 243, 115, 33 },
    KRONE = { 46, 125, 50 }, LEMKEN = { 0, 92, 169 }, POETTINGER = { 0, 150, 64 },
    KUHN = { 226, 0, 26 }, JCB = { 252, 179, 21 }, MANITOU = { 227, 6, 19 },
    CHALLENGER = { 246, 184, 0 }, STEYR = { 200, 16, 46 },
}

-- Brands whose logo is white or very pale, measured on the game's own logos (light share of the
-- opaque pixels 0.5 or more, or a mean luminance of 0.75 or more).
SdBrands.LIGHT_LOGOS = {}
for _, name in ipairs({
    "AGRIFAC", "APV", "APE", "CONVEYALL", "DALBO", "ELHO", "SKODA", "FARMTECH", "FENDT", "GEA", "GOLDHOFER",
    "HUSQVARNA", "INTERNATIONAL", "KOMATSU", "KOTTE", "KRAMPE", "LACOTEC", "LEMKEN", "LODEKING", "MACDON", "MACK",
    "MERCEDESBENZTRUCKS", "MERIDIAN", "MITAS", "NEWHOLLAND", "PORSCHEDIESEL", "QUICKE", "RANDON", "ROSTSELMASH",
    "ROTTNE", "SALFORD", "SCHAEFFER", "SENNEBOGEN", "TAJFUN", "TROUTRIVER", "VALTRA", "VOLVO", "VREDESTEIN", "WELGER",
    "MZURI", "NARDI", "FLEXICOIL", "DAMMANN", "JUNGHEINRICH", "KESLA", "NEXAT", "OLOFSFORS", "HOLMER", "MERLO", "DFM",
    "HEIZOMAT", "SUMMERSMFG", "BOMECH", "BRANDT", "LIZARD", "UNVERFERTH", "SCHWARZMUELLER", "FARMAX", "GORENC",
    "ARMATRAC", "RIGITRAC", "BRIELMAIER", "TMCCANCELA", "AGIWESTFIELD", "AGCO", "ARCUSIN", "MICHELIN", "WEBERMT",
    "FARMET", "PROVITIS", "AGISENTINEL", "HELM", "JMMANUFACTURING", "ABI", "AGIWESTEEL", "WILSON", "DUEVELSDORF",
    "WARZEE", "ANDERSONGROUP", "REITER", "KRAMER", "AGISTORM", "PALADIN", "RIEDLER", "AGIBATCO", "GIANTS",
    "ANNABURGER", "STEPA", "TRELLEBORG", "AGINECO", "AGRISPREAD", "MCCULLOCH", "NEUERO", "KAERCHER",
    "KRONE", "CHALLENGER", "AGRISEM", "RAU", "ZIEGLER",
}) do SdBrands.LIGHT_LOGOS[name] = true end

-- Board face colours, linear: white, and the dark grey behind a light logo.
SdBrands.FACE_WHITE = { 0.80, 0.80, 0.78 }
SdBrands.FACE_DARK = { 0.025, 0.027, 0.032 }
-- A brand colour darker than this (linear luminance) carries a light logo itself.
SdBrands.DARK_ENOUGH = 0.18


--- sRGB 0-255 to the shader's linear 0-1. Pure.
function SdBrands.linear(rgb)
    local out = {}
    for i = 1, 3 do
        local c = (rgb[i] or 0) / 255
        out[i] = c <= 0.04045 and c / 12.92 or ((c + 0.055) / 1.055) ^ 2.4
    end
    return out
end


--- A colour from a value the game might hold it in: { r, g, b }, {r=, g=, b=} or "r g b". Pure.
function SdBrands.readColour(value)
    if type(value) == "string" then
        local r, g, b = string.match(value, "^%s*([%d%.%-]+)[%s,]+([%d%.%-]+)[%s,]+([%d%.%-]+)")
        if r ~= nil then return { tonumber(r), tonumber(g), tonumber(b) } end
    elseif type(value) == "table" then
        local r, g, b = value[1] or value.r, value[2] or value.g, value[3] or value.b
        if type(r) == "number" and type(g) == "number" and type(b) == "number" then return { r, g, b } end
    end
    return nil
end


--- How colourful a linear colour is: 0 for white, grey and black. Pure.
function SdBrands.saturation(c)
    local hi, lo = math.max(c[1], c[2], c[3]), math.min(c[1], c[2], c[3])
    if hi <= 0.002 then return 0 end
    return (hi - lo) / hi
end


--- The brand's own colour from named paints: the most colourful one whose name starts with the
--- brand's ("fendtNatureGreen" for FENDT). Pure.
function SdBrands.pickPaint(brand, paints)
    local key = string.lower(string.gsub(brand or "", "[^%w]", ""))
    if key == "" then return nil end
    local best, bestName, bestSat = nil, nil, 0.25
    for name, colour in pairs(paints) do
        local plain = string.lower(string.gsub(name, "[^%w]", ""))
        if string.sub(plain, 1, #key) == key then
            local sat = SdBrands.saturation(colour)
            if sat > bestSat or (sat == bestSat and bestName ~= nil and name < bestName) then
                best, bestName, bestSat = colour, name, sat
            end
        end
    end
    return best, bestName
end


SdBrands.PAINT_SOURCES = {
    { manager = "g_vehicleMaterialManager", tables = { "materialTemplates", "templates", "nameToTemplate", "materialTemplateByName" } },
    { manager = "g_materialManager", tables = { "materialTemplates", "templates", "nameToTemplate" } },
    { manager = "g_brandColorManager", tables = { "brandColors", "colors", "nameToColor" } },
}
SdBrands.COLOUR_FIELDS = { "colorScale", "colourScale", "color", "colour", "baseColor", "diffuseColor" }


local function colourOf(entry)
    local direct = SdBrands.readColour(entry)
    if direct ~= nil then return direct end
    if type(entry) ~= "table" then return nil end
    for _, field in ipairs(SdBrands.COLOUR_FIELDS) do
        local c = SdBrands.readColour(entry[field])
        if c ~= nil then return c end
    end
    local params = entry.parameters or entry.customParameters or entry.shaderParameters
    if type(params) == "table" then
        for _, field in ipairs(SdBrands.COLOUR_FIELDS) do
            local p = params[field]
            local c = SdBrands.readColour(type(p) == "table" and (p.value or p) or p)
            if c ~= nil then return c end
        end
    end
    return nil
end


--- The game's named paints, read once.
function SdBrands.gamePaints()
    if SdBrands.paints ~= nil then return SdBrands.paints end
    local paints, source = {}, nil
    for _, src in ipairs(SdBrands.PAINT_SOURCES) do
        local manager = _G[src.manager]
        if type(manager) == "table" then
            for _, field in ipairs(src.tables) do
                local list = manager[field]
                if type(list) == "table" then
                    local count = 0
                    for key, entry in pairs(list) do
                        local name = type(key) == "string" and key or (type(entry) == "table" and entry.name) or nil
                        local colour = type(name) == "string" and colourOf(entry) or nil
                        if colour ~= nil then
                            paints[name] = colour
                            count = count + 1
                        end
                    end
                    if count > 0 then
                        source = string.format("%s.%s (%d)", src.manager, field, count)
                        break
                    end
                end
            end
        end
        if source ~= nil then break end
    end
    SdBrands.paints = paints
    Log:info("brand paints from %s", tostring(source or "our own list"))
    return paints
end


--- @param brand string|nil
--- @return table|nil the brand's colour, linear
function SdBrands.colour(brand)
    if type(brand) ~= "string" or brand == "" then return nil end
    SdBrands.cache = SdBrands.cache or {}
    if SdBrands.cache[brand] ~= nil then return SdBrands.cache[brand].colour end
    local colour = nil
    local own = SdBrands.OWN_COLOURS[string.upper(brand)]
    if own ~= nil then
        colour = SdBrands.linear(own)
    else
        -- our list first: a brand's paints can hold a brighter second colour (John Deere yellow)
        if SdBrands.COLOURS[string.upper(brand)] ~= nil then
            colour = SdBrands.linear(SdBrands.COLOURS[string.upper(brand)])
        else
            local ok, paints = SdLog.try("brand paints", SdBrands.gamePaints)
            if ok and type(paints) == "table" then colour = SdBrands.pickPaint(brand, paints) end
        end
    end
    SdBrands.cache[brand] = { colour = colour }
    return colour
end


--- @param brand string|nil
--- @return table the board colour behind its logo: white, or for a light logo the brand's own
--- colour when dark enough, else dark grey
function SdBrands.faceColour(brand)
    if brand ~= nil and SdBrands.OWN_COLOURS[string.upper(brand)] ~= nil then
        return SdBrands.linear(SdBrands.OWN_COLOURS[string.upper(brand)])
    end
    if brand == nil or not SdBrands.LIGHT_LOGOS[string.upper(brand)] then return SdBrands.FACE_WHITE end
    local colour = SdBrands.colour(brand)
    if colour ~= nil and 0.2126 * colour[1] + 0.7152 * colour[2] + 0.0722 * colour[3] < SdBrands.DARK_ENOUGH then
        return colour
    end
    return SdBrands.FACE_DARK
end


--- @return table name -> brand, and a sorted list of names: the game's brands with a logo
function SdBrands.all()
    local byName, names = {}, {}
    local manager = g_brandManager
    local list = manager ~= nil and (manager.indexToBrand or manager.nameToBrand) or {}
    for _, brand in pairs(list) do
        if type(brand) == "table" and brand.name ~= nil and type(brand.image) == "string" and brand.image ~= "" then
            if byName[brand.name] == nil then table.insert(names, brand.name) end
            byName[brand.name] = brand
        end
    end
    table.sort(names)
    return byName, names
end


--- @param vehicle table
--- @return string|nil its brand's name
function SdBrands.of(vehicle)
    if vehicle == nil or vehicle.configFileName == nil or g_storeManager == nil or g_brandManager == nil then return nil end
    local item = g_storeManager:getItemByXMLFilename(vehicle.configFileName)
    local brand = item ~= nil and item.brandIndex ~= nil and g_brandManager:getBrandByIndex(item.brandIndex) or nil
    return brand ~= nil and brand.name or nil
end


--- A brand picked for a display with nothing on it: the same one for the same spot. Pure.
--- @param names table sorted brand names
--- @param x number the display's position
--- @param z number
--- @return string|nil
function SdBrands.pick(names, x, z)
    if #names == 0 then return nil end
    local seed = math.floor((x or 0) * 7.31 + (z or 0) * 13.17)
    return names[(seed % #names) + 1]
end
