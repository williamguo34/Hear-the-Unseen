/*
  Hear the Unseen Uno firmware: MPU6500-compatible 6-axis I2C IMU
  + optional QMC5883P + V919 vibration module + pushbutton.

  Wiring on Arduino Uno:
    MPU module: GND -> GND, SDA -> A4, SCL -> A5
    MPU AD0 -> GND (I2C address 0x68); XDA/XCL/INT unused.
    MPU VCC -> the supply voltage verified for the actual module.
    V919 VCC -> 5V, GND -> GND, IN -> D9
    Pushbutton: one side -> D2, other side -> GND
    Optional QMC5883P: SDA -> A4, SCL -> A5, GND -> common GND.
    Keep sensor module supply voltages as verified on the actual boards.
    The two sensor boards share SDA/SCL; QMC5883P DRDY is unused.

  USB serial at 230400 sends samples at 200 Hz in the format expected by
  server.py:
    IMU,device_micros,gx_deg_s,gy_deg_s,gz_deg_s,ax_g,ay_g,az_g
  When the magnetometer is available, also sends at most 10 Hz:
    MAG,device_micros,mx_raw,my_raw,mz_raw
  Magnetic readings are raw sensor-frame counts, not fused or calibrated.

  Receiving BLOCK from the Mac produces a short full-strength V919 pulse.
  Pressing the button produces the same pulse and sends CALIBRATE so the Mac
  locks direction immediately. It does not run a still calibration.
  Receiving STILL waits 250 ms, then averages two seconds of gyro readings.
  Keep the saber still during that window. GYRO_READY marks the end.
*/

#include <Wire.h>

const uint8_t MPU_ADDR = 0x68;
const uint8_t QMC_ADDR = 0x2C;
const uint8_t VIBRATION_PIN = 9;  // PWM-capable on Uno
const uint8_t BUTTON_PIN = 2;

const uint8_t REG_SMPLRT_DIV = 0x19;
const uint8_t REG_CONFIG = 0x1A;
const uint8_t REG_GYRO_CONFIG = 0x1B;
const uint8_t REG_ACCEL_CONFIG = 0x1C;
const uint8_t REG_ACCEL_CONFIG2 = 0x1D;
const uint8_t REG_ACCEL_XOUT_H = 0x3B;
const uint8_t REG_PWR_MGMT_1 = 0x6B;
const uint8_t REG_WHO_AM_I = 0x75;

const unsigned long SAMPLE_PERIOD_US = 5000UL;  // 200 Hz
const unsigned long MAG_PERIOD_US = 100000UL;  // Optional raw telemetry, 10 Hz.
const unsigned long MPU_RETRY_US = 500000UL;
const unsigned long MPU_HEALTH_US = 250000UL;
const unsigned long MAG_RETRY_US = 1000000UL;
const unsigned long BLOCK_PULSE_US = 150000UL;  // 150 ms
const unsigned long BUTTON_DEBOUNCE_MS = 25UL;
const uint16_t GYRO_CALIBRATION_SAMPLES = 400;  // Two seconds at 200 Hz.
const unsigned long CALIBRATION_DELAY_US = 250000UL;
const uint8_t BLOCK_STRENGTH = 255;

unsigned long lastSampleUs = 0;
unsigned long lastMagUs = 0;
bool magAvailable = false;
bool mpuAvailable = false;
unsigned long lastMpuRetryUs = 0;
unsigned long lastMpuHealthUs = 0;
unsigned long lastMagRetryUs = 0;
unsigned long lastMagDataUs = 0;
char commandBuffer[16];
uint8_t commandLength = 0;
bool commandOverflow = false;
unsigned long vibrationOffUs = 0;
bool lastButtonReading = HIGH;
bool buttonState = HIGH;
unsigned long buttonChangedMs = 0;
bool gyroCalibrationActive = false;
unsigned long gyroCalibrationStartUs = 0;
uint16_t gyroCalibrationSamples = 0;
float gyroSumX = 0.0f;
float gyroSumY = 0.0f;
float gyroSumZ = 0.0f;
float gyroBiasX = 0.0f;
float gyroBiasY = 0.0f;
float gyroBiasZ = 0.0f;

void beginSensorBus() {
  Wire.begin();
  Wire.setClock(400000UL);
  Wire.setWireTimeout(50000UL, true);
  // Never enable the Uno's internal 5V pull-ups on the sensor bus.
  digitalWrite(A4, LOW);
  digitalWrite(A5, LOW);
  Wire.clearWireTimeoutFlag();
}

void releaseBusPin(uint8_t pin) {
  digitalWrite(pin, LOW);
  pinMode(pin, INPUT);  // External module pull-ups supply HIGH, not the Uno.
}

void waitForScl() {
  const unsigned long started = micros();
  while (digitalRead(A5) == LOW && micros() - started < 1000UL) {}
}

void recoverSensorBus() {
  Wire.end();
  releaseBusPin(A4);
  releaseBusPin(A5);
  // A slave interrupted mid-byte can hold SDA low; finish up to nine clocks.
  for (uint8_t i = 0; i < 9 && digitalRead(A4) == LOW; ++i) {
    pinMode(A5, OUTPUT);  // Output latch is LOW: open-drain style only.
    delayMicroseconds(5);
    releaseBusPin(A5);
    waitForScl();
    delayMicroseconds(5);
  }
  pinMode(A5, OUTPUT);
  pinMode(A4, OUTPUT);
  delayMicroseconds(5);
  releaseBusPin(A5);
  waitForScl();
  delayMicroseconds(5);
  releaseBusPin(A4);  // STOP: release SDA while SCL is high.
  beginSensorBus();
}

bool writeRegister(uint8_t reg, uint8_t value, uint8_t address = MPU_ADDR) {
  Wire.setClock(address == QMC_ADDR ? 50000UL : 400000UL);
  Wire.beginTransmission(address);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegisters(uint8_t reg, uint8_t *data, uint8_t count, uint8_t address = MPU_ADDR) {
  Wire.setClock(address == QMC_ADDR ? 50000UL : 400000UL);
  Wire.beginTransmission(address);
  Wire.write(reg);
  if (Wire.endTransmission(true) != 0) return false;

  const uint8_t received = Wire.requestFrom(address, count);
  if (received != count) {
    while (Wire.available()) Wire.read();
    return false;
  }
  for (uint8_t i = 0; i < count; ++i) data[i] = Wire.read();
  return true;
}

int16_t int16BigEndian(uint8_t highByte, uint8_t lowByte) {
  return static_cast<int16_t>((static_cast<uint16_t>(highByte) << 8) | lowByte);
}

bool setupMpu6500() {
  uint8_t whoAmI = 0;
  if (!readRegisters(REG_WHO_AM_I, &whoAmI, 1)) {
    Serial.println("ERROR,MPU,WHO_AM_I_READ_FAILED");
    return false;
  }
  Serial.print("STATUS,MPU,WHO_AM_I,0x"); Serial.println(whoAmI, HEX);
  if (whoAmI != 0x70) {
    Serial.println("ERROR,MPU,UNEXPECTED_ID");
    return false;
  }

  // PLL clock, then 200 Hz output with 41 Hz accel/gyro low-pass filters.
  return writeRegister(REG_PWR_MGMT_1, 0x01) &&
         writeRegister(REG_SMPLRT_DIV, 4) &&
         writeRegister(REG_CONFIG, 0x03) &&
         writeRegister(REG_GYRO_CONFIG, 0x08) &&  // +/-500 deg/s
         writeRegister(REG_ACCEL_CONFIG, 0x10) && // +/-8 g
         writeRegister(REG_ACCEL_CONFIG2, 0x03);  // 41 Hz accel DLPF
}

bool setupOptionalMag() {
  uint8_t id = 0;
  if (!readRegisters(0x00, &id, 1, QMC_ADDR) || id != 0x80) return false;
  // Use the settings verified in the joint hardware test; no soft reset.
  return writeRegister(0x0B, 0x08, QMC_ADDR) &&  // +/-8 gauss, set/reset on.
         writeRegister(0x0A, 0x03, QMC_ADDR);    // Continuous mode.
}

void disableMag() {
  if (magAvailable) Serial.println("STATUS,MAG,OFF");
  magAvailable = false;
  lastMagRetryUs = micros();
}

void markMpuOffline() {
  if (mpuAvailable) Serial.println("STATUS,MPU,OFF");
  mpuAvailable = false;
  lastMpuRetryUs = micros();
  disableMag();
}

bool mpuConfigurationValid() {
  uint8_t config[5];
  uint8_t power = 0;
  // Detect a power/reset event even when raw register reads still ACK.
  return readRegisters(REG_PWR_MGMT_1, &power, 1) && power == 0x01 &&
         readRegisters(REG_SMPLRT_DIV, config, sizeof(config)) &&
         config[0] == 4 && config[1] == 0x03 && config[2] == 0x08 &&
         config[3] == 0x10 && config[4] == 0x03;
}

void updateMag(unsigned long now) {
  if (!magAvailable) {
    if (static_cast<unsigned long>(now - lastMagRetryUs) < MAG_RETRY_US) return;
    lastMagRetryUs = now;
    magAvailable = setupOptionalMag();
    if (magAvailable) {
      lastMagDataUs = micros();
      Serial.println("STATUS,MAG,READY");
    }
    return;
  }
  if (static_cast<unsigned long>(now - lastMagUs) < MAG_PERIOD_US) return;
  lastMagUs = now;
  uint8_t status = 0;
  if (!readRegisters(0x09, &status, 1, QMC_ADDR)) {
    disableMag();
    return;
  }
  if (!(status & 0x03)) {
    // Power loss can reset continuous mode without making I2C reads fail.
    if (static_cast<unsigned long>(now - lastMagDataUs) >= MAG_RETRY_US) disableMag();
    return;
  }
  uint8_t raw[6];
  if (!readRegisters(0x01, raw, sizeof(raw), QMC_ADDR)) {
    disableMag();
    return;
  }
  if (status & 0x02) return;  // Reading clears overflow; discard invalid sample.
  lastMagDataUs = micros();
  Serial.print("MAG,"); Serial.print(micros());
  for (uint8_t i = 0; i < sizeof(raw); i += 2) {
    Serial.print(','); Serial.print(int16BigEndian(raw[i + 1], raw[i]));
  }
  Serial.println();
}

void triggerBlockFeedback() {
  analogWrite(VIBRATION_PIN, BLOCK_STRENGTH);
  vibrationOffUs = micros() + BLOCK_PULSE_US;
  digitalWrite(LED_BUILTIN, HIGH);
}

void updateVibration(unsigned long now) {
  if (vibrationOffUs != 0 && static_cast<long>(now - vibrationOffUs) >= 0) {
    analogWrite(VIBRATION_PIN, 0);
    vibrationOffUs = 0;
    digitalWrite(LED_BUILTIN, LOW);
  }
}

void startGyroCalibration() {
  gyroCalibrationActive = true;
  // The 150 ms haptic pulse finishes inside this 250 ms delay.
  gyroCalibrationStartUs = micros() + CALIBRATION_DELAY_US;
  gyroCalibrationSamples = 0;
  gyroSumX = 0.0f;
  gyroSumY = 0.0f;
  gyroSumZ = 0.0f;
  Serial.println("CALIBRATING");
}

void updateGyroCalibration(int16_t gx, int16_t gy, int16_t gz) {
  if (!gyroCalibrationActive) return;
  if (static_cast<long>(micros() - gyroCalibrationStartUs) < 0) return;

  gyroSumX += gx;
  gyroSumY += gy;
  gyroSumZ += gz;
  gyroCalibrationSamples++;

  if (gyroCalibrationSamples < GYRO_CALIBRATION_SAMPLES) return;

  gyroBiasX = gyroSumX / gyroCalibrationSamples;
  gyroBiasY = gyroSumY / gyroCalibrationSamples;
  gyroBiasZ = gyroSumZ / gyroCalibrationSamples;
  gyroCalibrationActive = false;
  Serial.println("GYRO_READY");
}

void updateButton() {
  const bool reading = digitalRead(BUTTON_PIN);
  const unsigned long nowMs = millis();

  if (reading != lastButtonReading) buttonChangedMs = nowMs;

  if (nowMs - buttonChangedMs >= BUTTON_DEBOUNCE_MS && reading != buttonState) {
    buttonState = reading;
    if (buttonState == LOW) {
      triggerBlockFeedback();  // INPUT_PULLUP: pressed is LOW.
      Serial.println("CALIBRATE");
    }
  }

  lastButtonReading = reading;
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(VIBRATION_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  analogWrite(VIBRATION_PIN, 0);
  Serial.begin(230400);
  Serial.println("BOOT,HearTheUnseen");
  beginSensorBus();
  delay(1000);
  mpuAvailable = setupMpu6500();
  if (!mpuAvailable) {
    Serial.println("ERROR,MPU,INIT_FAILED");
    Serial.println("STATUS,MPU,OFF");
  } else {
    Serial.println("READY,HearTheUnseen,MPU6500,V919");
    Serial.println("STATUS,MPU,READY");
  }
  magAvailable = mpuAvailable && setupOptionalMag();
  lastMpuRetryUs = lastMpuHealthUs = lastMagRetryUs = lastMagDataUs = micros();
  Serial.println(magAvailable ? "STATUS,MAG,READY" : "STATUS,MAG,OFF");
}

void loop() {
  unsigned long now = micros();
  updateButton();
  updateVibration(now);
  if (Wire.getWireTimeoutFlag()) {
    // A Wire timeout resets the controller and can re-enable internal pull-ups.
    digitalWrite(A4, LOW);
    digitalWrite(A5, LOW);
    Wire.clearWireTimeoutFlag();
    markMpuOffline();
  }

  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\n') {
      commandBuffer[commandLength] = '\0';
      if (!commandOverflow && strcmp(commandBuffer, "BLOCK") == 0) triggerBlockFeedback();
      else if (!commandOverflow && strcmp(commandBuffer, "STILL") == 0) startGyroCalibration();
      commandLength = 0;
      commandOverflow = false;
    } else if (c != '\r') {
      if (commandLength < sizeof(commandBuffer) - 1) commandBuffer[commandLength++] = c;
      else commandOverflow = true;
    }
  }

  if (!mpuAvailable) {
    if (static_cast<unsigned long>(now - lastMpuRetryUs) < MPU_RETRY_US) return;
    lastMpuRetryUs = now;
    recoverSensorBus();
    mpuAvailable = setupMpu6500();
    if (!mpuAvailable) return;  // Keep servicing button/motor and retry later.
    Serial.println("STATUS,MPU,READY");
    lastMpuHealthUs = micros();
    // Do not mix calibration samples from opposite sides of an interruption.
    // Keep the previous completed bias; restart a pending fixed-size window.
    if (gyroCalibrationActive) startGyroCalibration();
  }
  now = micros();
  updateVibration(now);
  if (static_cast<unsigned long>(now - lastMpuHealthUs) >= MPU_HEALTH_US) {
    lastMpuHealthUs = now;
    if (!mpuConfigurationValid()) {
      markMpuOffline();
      return;
    }
  }

  if (static_cast<unsigned long>(now - lastSampleUs) < SAMPLE_PERIOD_US) return;
  lastSampleUs = now;

  uint8_t raw[14];
  if (!readRegisters(REG_ACCEL_XOUT_H, raw, sizeof(raw))) {
    markMpuOffline();
    return;
  }

  const int16_t ax = int16BigEndian(raw[0], raw[1]);
  const int16_t ay = int16BigEndian(raw[2], raw[3]);
  const int16_t az = int16BigEndian(raw[4], raw[5]);
  const int16_t gx = int16BigEndian(raw[8], raw[9]);
  const int16_t gy = int16BigEndian(raw[10], raw[11]);
  const int16_t gz = int16BigEndian(raw[12], raw[13]);

  updateGyroCalibration(gx, gy, gz);

  // Scales correspond to the configured +/-8 g and +/-500 deg/s ranges.
  Serial.print("IMU,"); Serial.print(now);
  Serial.print(','); Serial.print((gx - gyroBiasX) / 65.5f, 2);
  Serial.print(','); Serial.print((gy - gyroBiasY) / 65.5f, 2);
  Serial.print(','); Serial.print((gz - gyroBiasZ) / 65.5f, 2);
  Serial.print(','); Serial.print(ax / 4096.0f, 3);
  Serial.print(','); Serial.print(ay / 4096.0f, 3);
  Serial.print(','); Serial.println(az / 4096.0f, 3);
  updateMag(micros());
}
