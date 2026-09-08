-- LightSaber iPhone IMU + haptic for TouchOSC (iPhone 13).
-- Paste this onto the document root if you create the layout by hand.
--
-- TouchOSC Connections → OSC:
--   Host        = Mac LAN IP printed by ./run_saber.zsh
--   Send Port   = 8000
--   Receive Port= 9000
--
-- getGyroscope() follows Core Motion and is rad/s. Convert to deg/s so the
-- Mac swing threshold (160°/s) matches the old Uno/MPU6050 firmware.
-- getAccelerometer() examples are m/s²; convert to g when gravity-sized.

local RAD2DEG = 180 / math.pi
local G = 9.80665

function onReceiveOSC(message, connections)
  local path = message[1]
  if path == '/vibrate' or path == '/block' then
    vibrate()
    return true
  end
end

function update()
  local gx, gy, gz = 0, 0, 0
  local ax, ay, az = 0, 0, 0
  if hasGyroscope() then
    gx, gy, gz = table.unpack(getGyroscope())
    gx, gy, gz = gx * RAD2DEG, gy * RAD2DEG, gz * RAD2DEG
  end
  if hasAccelerometer() then
    ax, ay, az = table.unpack(getAccelerometer())
    local mag = math.sqrt(ax * ax + ay * ay + az * az)
    if mag > 4 then
      ax, ay, az = ax / G, ay / G, az / G
    end
  end
  sendOSC('/imu', gx, gy, gz, ax, ay, az, getMillis())
  local omega = math.sqrt(gx * gx + gy * gy + gz * gz)
  local label = self.children.omega
  if label then
    label.values.text = string.format('%.0f°/s', omega)
  end
end
