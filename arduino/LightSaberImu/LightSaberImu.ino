/*
  LightSaber Uno firmware: mature Adafruit MPU6050 + DRV2605L libraries.

  Install from Arduino Library Manager before uploading:
    Adafruit MPU6050, Adafruit Unified Sensor, Adafruit BusIO, Adafruit DRV2605

  I2C wiring on Arduino Uno:
    MPU6050 SDA -> A4, SCL -> A5, VCC -> 5V, GND -> GND
    DRV2605L SDA -> A4, SCL -> A5, VIN -> 5V, GND -> GND
  Connect the DRV2605L to a compatible vibration motor/LRA as documented by its board.

  USB serial at 115200 sends raw gyro samples at 200 Hz. The Mac owns the
  swing threshold so changing it needs no reflash. Receiving BLOCK plays a
  short DRV2605L haptic effect and flashes the Uno's built-in LED.
*/

#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_DRV2605.h>

Adafruit_MPU6050 mpu;
Adafruit_DRV2605 haptic;
bool hapticReady = false;
const unsigned long SAMPLE_PERIOD_US = 5000;  // 200 Hz
unsigned long lastSampleUs = 0;
unsigned long ledOffUs = 0;

void playBlockFeedback() {
  digitalWrite(LED_BUILTIN, HIGH);
  ledOffUs = micros() + 25000UL;
  if (hapticReady) {
    haptic.setWaveform(0, 1);  // strong click, 100%
    haptic.setWaveform(1, 0);  // end marker
    haptic.go();
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  Wire.begin();

  if (!mpu.begin()) {
    while (true) {  // clear failure signal if MPU6050 wiring is absent
      digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
      delay(120);
    }
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);

  hapticReady = haptic.begin();
  if (hapticReady) {
    haptic.selectLibrary(6);  // LRA effects library
    haptic.useLRA();
  }
  Serial.println("READY,LightSaberImu");
}

void loop() {
  if (ledOffUs != 0 && (long)(micros() - ledOffUs) >= 0) {
    digitalWrite(LED_BUILTIN, LOW);
    ledOffUs = 0;
  }

  while (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command == "BLOCK") playBlockFeedback();
  }

  const unsigned long now = micros();
  if ((unsigned long)(now - lastSampleUs) < SAMPLE_PERIOD_US) return;
  lastSampleUs = now;

  sensors_event_t accel, gyro, temperature;
  mpu.getEvent(&accel, &gyro, &temperature);
  const float radiansToDegrees = 180.0f / PI;
  Serial.print("IMU,"); Serial.print(now);
  Serial.print(','); Serial.print(gyro.gyro.x * radiansToDegrees, 2);
  Serial.print(','); Serial.print(gyro.gyro.y * radiansToDegrees, 2);
  Serial.print(','); Serial.print(gyro.gyro.z * radiansToDegrees, 2);
  Serial.print(','); Serial.print(accel.acceleration.x / 9.80665f, 3);
  Serial.print(','); Serial.print(accel.acceleration.y / 9.80665f, 3);
  Serial.print(','); Serial.println(accel.acceleration.z / 9.80665f, 3);
}
