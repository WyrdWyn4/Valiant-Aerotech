local STABILIZE_BUTTON_RC = 5
local SWITCH_LOW_THRESHOLD = 1300
local POLL_MS = 100
local ALTITUDE_THRESHOLD_M = 1.0
local STABILIZE = 9

local function stabilize()
    local pwm = rc and rc.get_pwm and rc:get_pwm(STABILIZE_BUTTON_RC) or 1500

    if pwm > SWITCH_LOW_THRESHOLD and vehicle:get_mode() ~= STABILIZE then
        gcs:send_text(4, string.format("stabilize: Setting mode to STABILIZE."))
        vehicle:set_mode(STABILIZE)
    end
    
    return stabilize(), POLL_MS
end

return stabilize(), POLL_MS