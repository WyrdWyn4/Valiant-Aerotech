--[[
   Simple altitude test script for copter
   Sequence:
   1. Arm vehicle
   2. Wait 3 seconds
   3. Take off to 0.0625m, stay 10 seconds
   4. Go to 0.125m, stay 10 seconds
   5. Return to 0.0625m, stay 10 seconds
   6. Land and disarm
--]]

local stage = 0
local stage_start_time = 0
local prev_armed = false
local copter_guided_mode_num = 4
local copter_land_mode_num = 9

-- Stage definitions
local STAGE_IDLE = 0
local STAGE_WAIT_3_BEFORE_TAKEOFF = 1
local STAGE_TAKEOFF_TO_0625 = 2
local STAGE_HOLD_0625_FIRST = 3
local STAGE_TAKEOFF_TO_125 = 4
local STAGE_HOLD_125 = 5
local STAGE_DESCEND_TO_0625 = 6
local STAGE_HOLD_0625_SECOND = 7
local STAGE_LAND = 8
local STAGE_DONE = 9

function update()
    local now = millis():tofloat() * 0.001  -- Convert to seconds
    local is_armed = arming:is_armed()

    gcs:send_text(6, "Scripting: Stage "..stage..", Time: "..string.format("%.2f", now)..", Armed: "..tostring(is_armed))
    
    -- Detect arming transition
    if not prev_armed and is_armed then
        stage_start_time = now
        stage = STAGE_WAIT_3_BEFORE_TAKEOFF
        gcs:send_text(6, "Scripting: Armed! Waiting 3 seconds before takeoff")
    end
    prev_armed = is_armed

    
    -- Stage: Wait 3 seconds before takeoff
    if stage == STAGE_WAIT_3_BEFORE_TAKEOFF then
        if now - stage_start_time >= 3 then
            -- Switch to Guided mode
            if vehicle:set_mode(copter_guided_mode_num) then
                stage_start_time = now
                stage = STAGE_TAKEOFF_TO_0625
                gcs:send_text(6, "Scripting: Taking off to 0.0625m")
            end
        end
    end
    
    -- Stage: Takeoff to 0.0625m
    if stage == STAGE_TAKEOFF_TO_0625 then
        vehicle:start_takeoff(0.0625)
        if has_reached_altitude(0.0625) then
            stage_start_time = now
            stage = STAGE_HOLD_0625_FIRST
            gcs:send_text(6, "Scripting: Reached 0.0625m, holding for 10 seconds")
        end
    end
    
    -- Stage: Hold at 0.0625m for 10 seconds
    if stage == STAGE_HOLD_0625_FIRST then
        vehicle:start_takeoff(0.0625)
        if now - stage_start_time >= 10 then
            stage_start_time = now
            stage = STAGE_TAKEOFF_TO_125
            gcs:send_text(6, "Scripting: Going to 0.125m")
        end
    end
    
    -- Stage: Takeoff to 0.125m
    if stage == STAGE_TAKEOFF_TO_125 then
        vehicle:start_takeoff(0.125)
        if has_reached_altitude(0.125) then
            stage_start_time = now
            stage = STAGE_HOLD_125
            gcs:send_text(6, "Scripting: Reached 0.125m, holding for 10 seconds")
        end
    end
    
    -- Stage: Hold at 0.125m for 10 seconds
    if stage == STAGE_HOLD_125 then
        vehicle:start_takeoff(0.125)
        if now - stage_start_time >= 10 then
            stage_start_time = now
            stage = STAGE_DESCEND_TO_0625
            gcs:send_text(6, "Scripting: Descending to 0.0625m")
        end
    end
    
    -- Stage: Descend to 0.0625m
    if stage == STAGE_DESCEND_TO_0625 then
        vehicle:start_takeoff(0.0625)
        if has_reached_altitude(0.0625) then
            stage_start_time = now
            stage = STAGE_HOLD_0625_SECOND
            gcs:send_text(6, "Scripting: Reached 0.0625m, holding for 10 seconds")
        end
    end
    
    -- Stage: Hold at 0.0625m for 10 seconds
    if stage == STAGE_HOLD_0625_SECOND then
        vehicle:start_takeoff(0.0625)
        if now - stage_start_time >= 10 then
            stage = STAGE_LAND
            gcs:send_text(6, "Scripting: Landing...")
        end
    end
    
    -- Stage: Land
    if stage == STAGE_LAND then
        if vehicle:set_mode(copter_land_mode_num) then
            stage = STAGE_DONE
            gcs:send_text(6, "Scripting: Script complete!")
        end
    end

    return update, 1000
end

-- Helper function to check if target altitude is reached
function has_reached_altitude(target_alt)
    local home = ahrs:get_home()
    local curr_loc = ahrs:get_position()
    if home and curr_loc then
        local vec_from_home = home:get_distance_NED(curr_loc)
        local current_alt = -vec_from_home:z()
        -- Check if within 0.05m of target
        if math.abs(current_alt - target_alt) < 0.05 then
            return true
        end
    end
    return false
end

-- Register update function to run at 10 Hz

return update()

