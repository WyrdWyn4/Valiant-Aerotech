-- Constants
local INTERVAL_MS = 100
local STAGE_DURATION_MS = 10000
local WAIT_BEFORE_TAKEOFF_MS = 3000

-- Safety Settings
local MAX_THROTTLE_THRESHOLD = 600  -- 60% (ArduPilot scales 0-1000)
local MAX_CLIMB_RATE_CMS = 50       -- 50 cm/s (Gentle climb)

-- Altitudes (meters)
local ALT_LOW  = 0.0625
local ALT_HIGH = 0.125

local EMERGENCY_BUTTON_RC = 8
local SWITCH_LOW_THRESHOLD = 1300
local POLL_MS = 100
local ALTITUDE_THRESHOLD_M = 1.0
local LAND = 9

local stage = 0
local stage_start_time = uint32_t(0)

-- Function to check if throttle is too high
function check_safety()
    -- 3 is the standard throttle channel index in ArduPilot
    local current_throttle = SRV_Channels:get_output_scaled(3)
    
    if current_throttle > MAX_THROTTLE_THRESHOLD then
        gcs:send_text(2, string.format("CRITICAL: Throttle %d exceeds limit!", current_throttle))
        vehicle:set_mode(9) -- Force LAND
        return false
    end
    return true
end

function update()
    -- 1. Hardware Safety Check: Ensure the watchdog passes
    if not check_safety() then
        return -- Stop rescheduling the script (kills the test)
    end

    local pwm = rc and rc.get_pwm and rc:get_pwm(EMERGENCY_BUTTON_RC) or 1500

    if pwm > SWITCH_LOW_THRESHOLD then
        gcs:send_text(4, "safety: EMERGENCY FLIP SWITCH ACTIVATED (HIGH -> LOW)!")
      
        if arming:is_armed() then
            if vehicle:get_mode() ~= LAND then
                gcs:send_text(4, string.format("safety: High alt. Setting mode to LAND."))
                vehicle:set_mode(LAND)
            end
            
            if not vehicle:get_likely_flying() then
                gcs:send_text(4, string.format("safety: Low alt or already landing. Initiating disarm."))
                arming:disarm()
            end

            return
        end
    end

    -- 2. Initialization & Parameter Setup
    if stage == 0 then
        -- Set a slow climb rate globally for this test
        param:set('PILOT_SPEED_UP', MAX_CLIMB_RATE_CMS)
        
        if arming:is_armed() then
            gcs:send_text(6, "Script: Arming Vehicle")
            stage_start_time = millis()
            stage = 1
        end
        return update, INTERVAL_MS
    end

    local timer = (millis() - stage_start_time):toint()

    -- 3. Mission Logic (State Machine)
    if stage == 1 then -- Wait after arming
        if timer > WAIT_BEFORE_TAKEOFF_MS then
            gcs:send_text(6, "Script: Taking off")
            vehicle:set_mode(4) -- GUIDED
            vehicle:start_takeoff(ALT_LOW)
            stage = 2
            stage_start_time = millis()
        end

    elseif stage == 2 then -- Stay at Low Alt
        if timer > STAGE_DURATION_MS then
            gcs:send_text(6, "Script: To 0.125m")
            local target = Vector3f()
            target:z(-ALT_HIGH) 
            vehicle:set_target_location_local(target)
            stage = 3
            stage_start_time = millis()
        end

    elseif stage == 3 then -- Stay at High Alt
        if timer > STAGE_DURATION_MS then
            gcs:send_text(6, "Script: Back to 0.0625m")
            local target = Vector3f()
            target:z(-ALT_LOW)
            vehicle:set_target_location_local(target)
            stage = 4
            stage_start_time = millis()
        end

    elseif stage == 4 then -- Stay at Low Alt then Land
        if timer > STAGE_DURATION_MS then
            gcs:send_text(6, "Script: Test finished. Landing.")
            vehicle:set_mode(9) -- LAND
            stage = 5
        end

    elseif stage == 5 then -- Disarm when on ground
        if not vehicle:get_is_flying() then
            arming:disarm()
            gcs:send_text(6, "Script: Sequence Complete")
            return -- End script
        end
    end

    return update, INTERVAL_MS
end

return update()