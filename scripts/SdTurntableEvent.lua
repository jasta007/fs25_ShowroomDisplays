--[[
    SdTurntableEvent.lua
    Multiplayer: the server tells every player where a turntable's disc is in its turn and whether
    it is turning, every few seconds (SdTurntable.SYNC_MS), so the disc each player sees matches
    the machines the server turns on it. Players turn it themselves in between.

    Part of Showroom Displays by Jasta007.
]]

SdTurntableEvent = {}

local SdTurntableEvent_mt = Class(SdTurntableEvent, Event)
InitEventClass(SdTurntableEvent, "SdTurntableEvent")


function SdTurntableEvent.emptyNew()
    return Event.new(SdTurntableEvent_mt)
end


--- @param placeable table the turntable
--- @param angle number its disc's turn, radians
--- @param spinning boolean
function SdTurntableEvent.new(placeable, angle, spinning)
    local event = SdTurntableEvent.emptyNew()
    event.placeable = placeable
    event.angle = angle
    event.spinning = spinning
    return event
end


function SdTurntableEvent:readStream(streamId, connection)
    self.placeable = NetworkUtil.readNodeObject(streamId)
    self.angle = streamReadFloat32(streamId)
    self.spinning = streamReadBool(streamId)
    self:run(connection)
end


function SdTurntableEvent:writeStream(streamId, connection)
    NetworkUtil.writeNodeObject(streamId, self.placeable)
    streamWriteFloat32(streamId, self.angle or 0)
    streamWriteBool(streamId, self.spinning == true)
end


function SdTurntableEvent:run(connection)
    -- only the server says how the disc turns
    if connection == nil or connection.getIsServer == nil or not connection:getIsServer() then return end
    SdLog.try("turntable sync", SdTurntable.onSync, self.placeable, self.angle, self.spinning)
end
