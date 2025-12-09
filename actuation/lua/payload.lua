local BUTTON_RC = 10
local SERVO_CH = 14
local POLL_MS = 100
local PRESS_THRESHOLD = 1700

local PWM_STATES = {
    1900, -- State 1
    1450, -- State 2
    1200, -- State 3
    1000, -- State 4
}

if not button_servo_states then
    button_servo_states = {
        state_idx = 1,
        last_pressed = false,
        initialized = false
    }
end

local function init()
    local s = button_servo_states
    gcs:send_text(0, string.format("payload: Initial state: PWM=%d", PWM_STATES[s.state_idx]))
    s.initialized = true
end

local function set_servo_pwm(pwm_value)
    local chan_idx = SERVO_CH - 1
    if SRV_Channels and SRV_Channels.set_output_pwm_chan_timeout then
        SRV_Channels:set_output_pwm_chan_timeout(chan_idx, pwm_value, 1000)
    elseif SRV_Channels and SRV_Channels.set_output_pwm then
        SRV_Channels:set_output_pwm(SERVO_CH, pwm_value)
    else
        gcs:send_text(2, "payload: SRV_Channels API not available")
    end
    gcs:send_text(0, string.format("payload: Move to state #%d -> PWM=%d", button_servo_states.state_idx, pwm_value))
end

local function update()
    local s = button_servo_states
    
    if not s.initialized then
        init()
        set_servo_pwm(PWM_STATES[s.state_idx])
    end

    local pwm = rc and rc.get_pwm and rc:get_pwm(BUTTON_RC) or 1000
    local pressed = pwm > PRESS_THRESHOLD

    if pressed and not s.last_pressed then
        s.state_idx = s.state_idx + 1
        if s.state_idx > #PWM_STATES then
            return
        end

        local new_pwm = PWM_STATES[s.state_idx]
        set_servo_pwm(new_pwm)
    end

    s.last_pressed = pressed

    return update, POLL_MS
end

return update, POLL_MS