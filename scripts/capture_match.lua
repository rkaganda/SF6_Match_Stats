-- local gameStateFormatPath = "env/game_env.format"
-- local gameStateFormatFile = io.open(gameStateFormatPath, "r")
-- local gameStateFormatString = gameStateFormatFile:read("*l")
local gameStateFormatString = "throw_invuln,hitstun,mEndFrame,current_HP,drive_cooldown,blockstun,HP_cooldown,chargeInfo,absolute_range,stance,drive,spdY,act_st,juggle,posY,pushback,aclY,mMarginFrame,mActionId,full_invuln,dir,spdX,posX,buff,super,aclX,mActionFrame,relative_range,HP_cap,hitstop"
local gameStateFormat = {}

local characterMapping = {
	["1"] = "Ryu",
	["2"] = "Luke",
	["3"] = "Kimberly",
	["4"] = "Chun-Li",
	["5"] = "Manon",
	["6"] = "Zangief",
	["7"] = "JP",
	["8"] = "Dhalsim",
	["9"] = "Cammy",
	["10"] = "Ken",
	["11"] = "Dee Jay",
	["12"] = "Lily",
	["14"] = "Rashid",
	["15"] = "Blanka",
	["16"] = "Juri",
	["17"] = "Marisa",
	["18"] = "Guile",
	["20"] = "E Honda",
	["21"] = "Jamie"
}

local gBattle
local p1 = {}
local p2 = {}
local replay_table = {}
local round_number = 0
local stage_timer = 0
local replay_saved = false
local data_reset = false
local display_capture_info

local filename_changed
local replay_filename = "replay.json"
local capture_status = "waiting for game..."

p1.absolute_range = 0
p1.relative_range = 0
p2.absolute_range = 0
p2.relative_range = 0


for value in string.gmatch(gameStateFormatString, "[^,]+") do
    table.insert(gameStateFormat, value)
end
--gameStateFormatFile:close()


function bitand(a, b)
    local result = 0
    local bitval = 1
    while a > 0 and b > 0 do
      if a % 2 == 1 and b % 2 == 1 then -- test the rightmost bits
          result = result + bitval      -- set the current bit
      end
      bitval = bitval * 2 -- shift left
      a = math.floor(a/2) -- shift right
      b = math.floor(b/2)
    end
    return result
end

local abs = function(num)
	if num < 0 then
		return num * -1
	else
		return num
	end
end

local function read_sfix(sfix_obj)
    if sfix_obj.w then
        return Vector4f.new(tonumber(sfix_obj.x:call("ToString()")), tonumber(sfix_obj.y:call("ToString()")), tonumber(sfix_obj.z:call("ToString()")), tonumber(sfix_obj.w:call("ToString()")))
    elseif sfix_obj.z then
        return Vector3f.new(tonumber(sfix_obj.x:call("ToString()")), tonumber(sfix_obj.y:call("ToString()")), tonumber(sfix_obj.z:call("ToString()")))
    elseif sfix_obj.y then
        return Vector2f.new(tonumber(sfix_obj.x:call("ToString()")), tonumber(sfix_obj.y:call("ToString()")))
    end
    return tonumber(sfix_obj:call("ToString()"))
end


function findMissingKeys(t)
    local minKey, maxKey = math.huge, -math.huge
    minKey = 0

    for k, v in pairs(t) do
        if type(k) ~= "number" then
            return nil, "Non-integer key detected"
        end
        if k > maxKey then maxKey = k end
    end

    local missingKeys = {}

    for i = minKey, maxKey do
        if not t[i] then
            table.insert(missingKeys, i)
        end
    end

    return missingKeys
end


local function writeReplayToFile()
    local filenameTimestamp = os.date("%Y%m%d_%H%M%S")
    local player0_name = characterMapping[tostring(replay_table['player_data']['player_0_id'])]
    local player1_name = characterMapping[tostring(replay_table['player_data']['player_1_id'])]
    local replay_filename = filenameTimestamp.."_"..player0_name.."_"..player1_name..".json"

    json.dump_file("recent_replay.json", replay_table)
    json.dump_file(replay_filename, replay_table)
    log.debug("recent_replay.json SAVED")

    -- if json.dump_file(replay_filename, replay_table) then
    --     re.msg("Saved "..replay_filename.." OK")
    -- else
    --     re.msg("Save Failed.")
    -- end
end




local function writeFrameToTable()
    if replay_table[round_number] == nil then
        replay_table[round_number] = {}
    end
    if replay_table[round_number][stage_timer] == nil then
        replay_table[round_number][stage_timer] = {}
    end

    replay_table[round_number][stage_timer]["p1"] = {}
    replay_table[round_number][stage_timer]["p2"] = {}

    for p_num=1, 2 do
        for i, gameEnvValue in ipairs(gameStateFormat) do
            if p_num == 1 then
                replay_table[round_number][stage_timer]["p1"][gameEnvValue] = p1[gameEnvValue]
            else
                replay_table[round_number][stage_timer]["p2"][gameEnvValue] = p2[gameEnvValue]
            end
        end
    end
end

re.on_script_reset(function()
end)


re.on_draw_ui(function()
    if imgui.tree_node("Capture Match") then
        changed, display_capture_info = imgui.checkbox("Display Capture Info", display_capture_info)
        imgui.tree_pop()
    end
end)

re.on_frame(function()
    gBattle = sdk.find_type_definition("gBattle")

    if display_capture_info then
        imgui.begin_window("Match Capture", true, 0)
        imgui.text("Status: "..capture_status)
        imgui.end_window()
    end
    if gBattle then
        local sRound = gBattle:get_field("Round"):get_data(nil) -- get round number
        local sGame = gBattle:get_field("Game"):get_data(nil) -- get game timer

        if sGame.fight_st ~=0 then
            log.debug("sGame.fight_st"..sGame.fight_st)

            round_number = sRound.RoundNo
            stage_timer = sGame.stage_timer
            local capture_frame = false

            local sPlayer = gBattle:get_field("Player"):get_data(nil)
            local cPlayer = sPlayer.mcPlayer
            local BattleTeam = gBattle:get_field("Team"):get_data(nil)
            local cTeam = BattleTeam.mcTeam
            -- Charge Info
            local storageData = gBattle:get_field("Command"):get_data(nil).StorageData
            local p1ChargeInfo = storageData.UserEngines[0].m_charge_infos
            local p2ChargeInfo = storageData.UserEngines[1].m_charge_infos
            -- Fireball
            local sWork = gBattle:get_field("Work"):get_data(nil)
            local cWork = sWork.Global_work
            -- Action States
            local p1Engine = gBattle:get_field("Rollback"):get_data():GetLatestEngine().ActEngines[0]._Parent._Engine
            local p2Engine = gBattle:get_field("Rollback"):get_data():GetLatestEngine().ActEngines[1]._Parent._Engine


            -- game done
            if sGame.fight_st == 7 and not replay_saved and data_reset then
                writeReplayToFile()
                replay_saved = true
                replay_table = {}
                replay_table['player_data'] = {}
                capture_frame = false
                capture_status = "game captured."
            -- game started
            elseif sGame.fight_st == 2 then
                replay_table = {}
                replay_table['player_data'] = {}
                replay_saved = false
                data_reset = true
                capture_status = "waiting for game..."
                capture_frame = false
                log.debug("reset replay")
            elseif sGame.fight_st == 3 then
                replay_table[round_number] = {}
                replay_saved = false
                data_reset = true
                capture_frame = false
                capture_status = "round reset."
                log.debug("reset round")
            elseif sGame.fight_st == 4 then
                capture_status = "capturing..."
                capture_frame = true
            end

            if not replay_table['player_data'] then
                replay_table['player_data'] = {}
            end

            if sPlayer.mPlayerType[0].mValue then
                replay_table['player_data']['player_0_id'] = sPlayer.mPlayerType[0].mValue
            end
            if sPlayer.mPlayerType[1].mValue then
                replay_table['player_data']['player_1_id'] = sPlayer.mPlayerType[1].mValue
            end

            -- p1.mActionId = cPlayer[0].mActionId
            p1.mActionId = p1Engine:get_ActionID()
            p1.mActionFrame = math.floor(read_sfix(p1Engine:get_ActionFrame()))
            p1.mEndFrame = math.floor(read_sfix(p1Engine:get_ActionFrameNum()))
            p1.mMarginFrame = math.floor(read_sfix(p1Engine:get_MarginFrame()))
            p1.HP_cap = cPlayer[0].vital_old
            p1.current_HP = cPlayer[0].vital_new
            p1.HP_cooldown = cPlayer[0].healing_wait
            p1.dir = bitand(cPlayer[0].BitValue, 128) == 128
            p1.dir = p1.dir and 1 or 0 -- bool to int conversion
            p1.hitstop = cPlayer[0].hit_stop
            p1.hitstun = cPlayer[0].damage_time
            p1.blockstun = cPlayer[0].guard_time
            p1.stance = cPlayer[0].pose_st
            p1.throw_invuln = cPlayer[0].catch_muteki
            p1.full_invuln = cPlayer[0].muteki_time
            p1.juggle = cPlayer[0].combo_dm_air
            p1.drive = cPlayer[0].focus_new
            p1.drive_cooldown = cPlayer[0].focus_wait
            p1.super = cTeam[0].mSuperGauge
            p1.buff = cPlayer[0].style_timer
            p1.posX = cPlayer[0].pos.x.v / 6553600.0
            p1.posY = cPlayer[0].pos.y.v / 6553600.0
            p1.spdX = cPlayer[0].speed.x.v / 6553600.0
            p1.spdY = cPlayer[0].speed.y.v / 6553600.0
            p1.aclX = cPlayer[0].alpha.x.v / 6553600.0
            p1.aclY = cPlayer[0].alpha.y.v / 6553600.0
            p1.pushback = cPlayer[0].vector_zuri.speed.v / 6553600.0
            p1.act_st = cPlayer[0].act_st


            p2.mActionId = cPlayer[1].mActionId
            p2.mActionId = p2Engine:get_ActionID()
            p2.mActionFrame = math.floor(read_sfix(p2Engine:get_ActionFrame()))
            p2.mEndFrame = math.floor(read_sfix(p2Engine:get_ActionFrameNum()))
            p2.mMarginFrame = math.floor(read_sfix(p2Engine:get_MarginFrame()))
            p2.HP_cap = cPlayer[1].vital_old
            p2.current_HP = cPlayer[1].vital_new
            p2.HP_cooldown = cPlayer[1].healing_wait
            p2.dir = bitand(cPlayer[1].BitValue, 128) == 128
            p2.dir = p2.dir and 1 or 0 -- bool to int conversion
            p2.hitstop = cPlayer[1].hit_stop
            p2.hitstun = cPlayer[1].damage_time
            p2.blockstun = cPlayer[1].guard_time
            p2.stance = cPlayer[1].pose_st
            p2.throw_invuln = cPlayer[1].catch_muteki
            p2.full_invuln = cPlayer[1].muteki_time
            p2.juggle = cPlayer[1].combo_dm_air
            p2.drive = cPlayer[1].focus_new
            p2.drive_cooldown = cPlayer[1].focus_wait
            p2.super = cTeam[1].mSuperGauge
            p2.buff = cPlayer[1].style_timer

            p2.posX = cPlayer[1].pos.x.v / 6553600.0
            p2.posY = cPlayer[1].pos.y.v / 6553600.0
            p2.spdX = cPlayer[1].speed.x.v / 6553600.0
            p2.spdY = cPlayer[1].speed.y.v / 6553600.0
            p2.aclX = cPlayer[1].alpha.x.v / 6553600.0
            p2.aclY = cPlayer[1].alpha.y.v / 6553600.0
            p2.pushback = cPlayer[1].vector_zuri.speed.v / 6553600.0
            p2.act_st = cPlayer[1].act_st

            if round_number and stage_timer and capture_frame then
                writeFrameToTable()
            end
        end
    end
end)
