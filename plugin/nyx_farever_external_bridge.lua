-- Nyx Farever External Bridge v0.11.1
--
-- Exports read-only live game state for an external desktop application.
-- Output files:
--   %LOCALAPPDATA%\farever-minimap\combatlogs\nyx_external_live_state.json
--   %LOCALAPPDATA%\farever-minimap\combatlogs\nyx_external_pois.json
--
-- Requires farever-minimap v1.1.7+ (tested against the v1.2.4 plugin API).

local LIVE_FILENAME = "nyx_external_live_state.json"
local POI_FILENAME  = "nyx_external_pois.json"
-- Five complete snapshots per second are enough for the standalone client's
-- interpolation while avoiding redundant API reads, JSON serialization, and
-- disk writes inside the game process.
local LIVE_INTERVAL = 0.20
local POI_INTERVAL  = 15.0

local last_live_write = -1000.0
local last_poi_write  = -1000.0
local last_error = ""
local fight_id = 0
local damage_skills = {}
local healing_skills = {}

local function json_string(value)
    local s = tostring(value or "")
    s = s:gsub('[%z\1-\31\\"]', function(c)
        if c == '"'  then return '\\"' end
        if c == '\\' then return '\\\\' end
        if c == '\b' then return '\\b' end
        if c == '\f' then return '\\f' end
        if c == '\n' then return '\\n' end
        if c == '\r' then return '\\r' end
        if c == '\t' then return '\\t' end
        return string.format('\\u%04x', string.byte(c))
    end)
    return '"' .. s .. '"'
end

local function json_number(value)
    local n = tonumber(value)
    if not n or n ~= n or n == math.huge or n == -math.huge then
        return "null"
    end
    return string.format("%.6f", n)
end

local function json_integer(value)
    local n = tonumber(value)
    if not n or n ~= n or n == math.huge or n == -math.huge then
        return "0"
    end
    return string.format("%d", math.floor(n))
end

local function json_bool(value)
    return value and "true" or "false"
end

local function metric_for(bucket, skill)
    local key = tostring(skill or "Unknown")
    local metric = bucket[key]
    if not metric then
        metric = { skill = key, total = 0.0, hits = 0, crits = 0, max = 0.0 }
        bucket[key] = metric
    end
    return metric
end

local function add_metric(bucket, skill, amount, is_crit)
    local metric = metric_for(bucket, skill)
    local value = tonumber(amount) or 0.0
    metric.total = metric.total + value
    metric.hits = metric.hits + 1
    if is_crit then metric.crits = metric.crits + 1 end
    if value > metric.max then metric.max = value end
end

local function metrics_json(bucket)
    local ordered = {}
    for _, metric in pairs(bucket) do
        ordered[#ordered + 1] = metric
    end
    table.sort(ordered, function(a, b)
        if a.total == b.total then return a.skill < b.skill end
        return a.total > b.total
    end)

    local out = {}
    for i, metric in ipairs(ordered) do
        out[i] = "{" ..
            "\"skill\":" .. json_string(metric.skill) .. "," ..
            "\"total\":" .. json_number(metric.total) .. "," ..
            "\"hits\":" .. json_integer(metric.hits) .. "," ..
            "\"crits\":" .. json_integer(metric.crits) .. "," ..
            "\"max\":" .. json_number(metric.max) ..
        "}"
    end
    return "[" .. table.concat(out, ",") .. "]"
end

local function party_json()
    local out = {}
    for i, member in ipairs(farever.party.list()) do
        out[i] = "{" ..
            "\"name\":" .. json_string(member.name) .. "," ..
            "\"class\":" .. json_string(member.class) .. "," ..
            "\"uid\":" .. json_string(member.uid) .. "," ..
            "\"x\":" .. json_number(member.x) .. "," ..
            "\"y\":" .. json_number(member.y) .. "," ..
            "\"z\":" .. json_number(member.z) .. "," ..
            "\"heading\":" .. json_number(member.rot_z) .. "," ..
            "\"hp\":" .. json_number(member.health) .. "," ..
            "\"max_hp\":" .. json_number(member.max_health) .. "," ..
            "\"attributes_valid\":" .. json_bool(member.attr_ok) .. "," ..
            "\"hero_valid\":" .. json_bool(member.hero_valid) ..
        "}"
    end
    return "[" .. table.concat(out, ",") .. "]"
end

local function build_live_json(now)
    local target_exists = farever.target.exists()
    local target_json = "{" ..
        "\"exists\":" .. json_bool(target_exists) .. "," ..
        "\"name\":" .. json_string(farever.target.name()) .. "," ..
        "\"level\":" .. json_integer(farever.target.level()) .. "," ..
        "\"x\":" .. json_number(farever.target.x()) .. "," ..
        "\"y\":" .. json_number(farever.target.y()) .. "," ..
        "\"z\":" .. json_number(farever.target.z()) .. "," ..
        "\"hp\":" .. json_number(farever.target.hp()) .. "," ..
        "\"max_hp\":" .. json_number(farever.target.max_hp()) .. "," ..
        "\"hp_pct\":" .. json_number(farever.target.hp_pct()) .. "," ..
        "\"is_casting\":" .. json_bool(farever.target.is_casting()) .. "," ..
        "\"cast_skill\":" .. json_string(farever.target.cast_skill()) .. "," ..
        "\"cast_elapsed\":" .. json_number(farever.target.cast_elapsed_sec()) .. "," ..
        "\"cast_total\":" .. json_number(farever.target.cast_total_sec()) .. "," ..
        "\"cast_remaining\":" .. json_number(farever.target.cast_remaining_sec()) .. "," ..
        "\"cast_progress\":" .. json_number(farever.target.cast_progress()) ..
    "}"

    return "{" ..
        "\"schema\":1," ..
        "\"bridge_version\":\"0.11.1\"," ..
        "\"source_time\":" .. json_number(now) .. "," ..
        "\"locked\":" .. json_bool(farever.player.locked()) .. "," ..
        "\"player\":{" ..
            "\"name\":" .. json_string(farever.player.name()) .. "," ..
            "\"class\":" .. json_string(farever.player.class()) .. "," ..
            "\"uid\":" .. json_string(farever.player.uid()) .. "," ..
            "\"level\":" .. json_integer(farever.player.level()) .. "," ..
            "\"x\":" .. json_number(farever.player.x()) .. "," ..
            "\"y\":" .. json_number(farever.player.y()) .. "," ..
            "\"z\":" .. json_number(farever.player.z()) .. "," ..
            "\"heading\":" .. json_number(farever.player.rot_z()) .. "," ..
            "\"hp\":" .. json_number(farever.player.health()) .. "," ..
            "\"max_hp\":" .. json_number(farever.player.max_health()) .. "," ..
            "\"hp_pct\":" .. json_number(farever.player.health_pct()) .. "," ..
            "\"hp_regen\":" .. json_number(farever.player.health_regen()) .. "," ..
            "\"shield\":" .. json_number(farever.player.shield()) .. "," ..
            "\"energy\":" .. json_number(farever.player.energy()) .. "," ..
            "\"energy_regen\":" .. json_number(farever.player.energy_regen()) .. "," ..
            "\"in_combat\":" .. json_bool(farever.player.in_combat()) ..
        "}," ..
        "\"dps\":{" ..
            "\"fight_id\":" .. json_integer(fight_id) .. "," ..
            "\"current\":" .. json_number(farever.dps.current()) .. "," ..
            "\"total\":" .. json_number(farever.dps.total()) .. "," ..
            "\"elapsed\":" .. json_number(farever.dps.elapsed()) .. "," ..
            "\"in_combat\":" .. json_bool(farever.dps.in_combat()) .. "," ..
            "\"damage_skills\":" .. metrics_json(damage_skills) .. "," ..
            "\"healing_skills\":" .. metrics_json(healing_skills) ..
        "}," ..
        "\"target\":" .. target_json .. "," ..
        "\"party\":" .. party_json() ..
    "}"
end

local function build_pois_json(now)
    local out = {}
    for i, poi in ipairs(farever.pois()) do
        out[i] = "{" ..
            "\"id\":" .. json_string(poi.id) .. "," ..
            "\"name\":" .. json_string(poi.name) .. "," ..
            "\"kind\":" .. json_string(poi.kind) .. "," ..
            "\"subkind\":" .. json_string(poi.subkind) .. "," ..
            "\"x\":" .. json_number(poi.x) .. "," ..
            "\"y\":" .. json_number(poi.y) .. "," ..
            "\"z\":" .. json_number(poi.z) ..
        "}"
    end
    return "{" ..
        "\"schema\":1," ..
        "\"source_time\":" .. json_number(now) .. "," ..
        "\"count\":" .. json_integer(#out) .. "," ..
        "\"pois\":[" .. table.concat(out, ",") .. "]" ..
    "}"
end

local function write_file(filename, contents)
    local path, err = farever.write_combatlog(filename, contents)
    if not path then
        last_error = tostring(err or "unknown write error")
        farever.log.warn("external bridge write failed: " .. last_error)
        return false
    end
    last_error = ""
    return true
end

function on_init()
    last_live_write = -1000.0
    last_poi_write = -1000.0
    last_error = ""
end

function on_event(name, data)
    if name == "hero_locked" then
        last_poi_write = -1000.0
    elseif name == "fight_start" then
        fight_id = tonumber(data.fight_id) or (fight_id + 1)
        damage_skills = {}
        healing_skills = {}
    elseif name == "damage_dealt" then
        add_metric(damage_skills, data.skill, data.amount, data.is_crit)
    elseif name == "heal_dealt" then
        add_metric(healing_skills, data.skill, data.amount, data.is_crit)
    end
end

function on_render()
    local now = farever.now()

    if now - last_live_write >= LIVE_INTERVAL then
        write_file(LIVE_FILENAME, build_live_json(now))
        last_live_write = now
    end

    if now - last_poi_write >= POI_INTERVAL then
        write_file(POI_FILENAME, build_pois_json(now))
        last_poi_write = now
    end

end
