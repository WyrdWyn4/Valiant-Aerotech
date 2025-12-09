local timer = 0
local armed_by_script = false

gcs:send_text(7, "DEBUG: ARM.LUA IS LOADING")

function update()
  gcs:send_text(6, "Script: Starting arming sequence")

  if not arming:is_armed() and not armed_by_script then
    if arming:arm() then
      gcs:send_text(6, "Script: Vehicle Armed")
      armed_by_script = true
    else
      gcs:send_text(6, "Script: Arming failed, retrying...")
    end

  elseif armed_by_script then
    timer = timer + 1
    gcs:send_text(6, "Script: Timer " .. tostring(timer))

    if timer >= 15 then
      arming:disarm()
      gcs:send_text(6, "Script: Disarmed complete")
      return
    end
  end

  return update, 1000
end

return update()