// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/*
 * The fixture class which maintains its internal states and performs
 * basic actions.
 */

#include "Arduino.h"
#include "Fixture.h"

// pins for jumper and debug button
const int pinJumper = 2;
const int pinButtonDebug = 3;

// sensor pins
const int pinSensorExtremeUp = 4;
const int pinSensorUp = 5;
const int pinSensorDown = 6;
const int pinSensorSafety = 7;

// pins to control the motor
const int pinMotorStep = 8;
const int pinMotorDir = 9;
const int pinMotorEn = 10;
const int pinMotorLock = 11;

// An array of sensor active values ranging from SENSOR_MIN to SENSOR_MAX.
const bool SENSOR_ACTIVE_VALUES[] = {HIGH, HIGH, HIGH, HIGH, HIGH, LOW};

// An array of sensor active times ranging from SENSOR_MIN to SENSOR_MAX.
// The value 0 indicates that a sensor is not active.
unsigned long SENSOR_ACTIVE_TIMES[] = {0, 0, 0, 0, 0, 0};

// An array of sensor active times ranging from SENSOR_MIN to SENSOR_MAX.
// The sensor active times must be longer than these values (in milli-seconds)
// to be considered as triggered.
// The active duration of the debug button is assigned a longer value
// to filter the mistakenly triggered button occasionally seen at factory
// due to unstable voltage.
// The active duration of safety sensor is assigned a shorter value for safety
// purpose.
unsigned const long SENSOR_ACTIVE_DURATIONS[] = {500, 500, 200, 200, 200, 100};

// The serial baud rate used by the programming port and the native USB port.
const int SERIAL_BAUD_RATE = 9600;

// Fixture states
// Initial state. This state is only possible when the arduino board
// is powered on or is reset.
const char stateInit = 'i';
// Motor is enabled and is going down.
const char stateGoingDown = 'd';
// Motor is enabled and is going up.
const char stateGoingUp = 'u';
// The probe stops at its Down position.
const char stateStopDown = 'D';
// The probe stops at its initial Up position.
const char stateStopUp = 'U';
// Motor is stopped as an emergency.
const char stateEmergencyStop = 'e';
// Motor is going back to the original up position after an emergency stop.
const char stateGoingUpAfterEmergency = 'b';

// The delay interval between two consecutive sensing.
const int SENSOR_DELAY_INTERVAL = 10;

// The values set on the pinMotorDir digital pin to control the motor direction.
const bool MOTOR_DIR_UP = LOW;
const bool MOTOR_DIR_DOWN = HIGH;

// Need to wait up to 2 seconds for all sensors and the motor to get ready.
const int WARM_UP_WAIT = 2000;


/**
 * Initialize some values and configure the pins.
 */
Fixture::Fixture() {
  state_ = stateInit;
  reset_count();
  pwmFrequency_ = 0;

  jumper_ = true;
  buttonDebug_ = false;
  sensorExtremeUp_ = false;
  sensorUp_ = false;
  sensorDown_ = false;
  sensorSafety_ = false;

  motorDir_ = MOTOR_DIR_UP;
  motorEn_ = LOW;
  motorLock_ = LOW;
  motorDutyCycle_ = false;

  // Initialize the jumper, the debug button, and the four sensor pins
  for (int sensor = SENSOR_MIN; sensor <= SENSOR_MAX; sensor++)
    pinMode(getPin((enum Sensors) sensor), INPUT);

  // Initialize the output pins for the motor control
  // Note: there is no need to configure pinMotorStep as OUTPUT
  //       when driving it with PWM.
  pinMode(pinMotorDir, OUTPUT);
  pinMode(pinMotorEn, OUTPUT);
  pinMode(pinMotorLock, OUTPUT);
}

/**
 * Overloading the assignment operator
 */
Fixture& Fixture::operator=(const Fixture &fixture) {
  state_ = fixture.state_;
  count_ = fixture.count_;
  pwmFrequency_ = fixture.pwmFrequency_;
  jumper_ = fixture.jumper_;
  buttonDebug_ = fixture.buttonDebug_;
  sensorExtremeUp_ = fixture.sensorExtremeUp_;
  sensorUp_ = fixture.sensorUp_;
  sensorDown_ = fixture.sensorDown_;
  sensorSafety_ = fixture.sensorSafety_;
  motorDir_ = fixture.motorDir_;
  motorEn_ = fixture.motorEn_;
  motorLock_ = fixture.motorLock_;
  motorDutyCycle_ = fixture.motorDutyCycle_;
  return *this;
}

/**
 * Overloading the equal operator
 */
bool Fixture::operator==(const Fixture &fixture) const {
  return (state_ == fixture.state_ &&
          pwmFrequency_ == fixture.pwmFrequency_ &&
          jumper_ == fixture.jumper_ &&
          buttonDebug_ == fixture.buttonDebug_ &&
          sensorExtremeUp_ == fixture.sensorExtremeUp_ &&
          sensorUp_ == fixture.sensorUp_ &&
          sensorDown_ == fixture.sensorDown_ &&
          sensorSafety_ == fixture.sensorSafety_ &&
          motorDir_ == fixture.motorDir_ &&
          motorEn_ == fixture.motorEn_ &&
          motorLock_ == fixture.motorLock_ &&
          motorDutyCycle_ == fixture.motorDutyCycle_);
}

/**
 * Overloading the not equal operator
 */
bool Fixture::operator!=(const Fixture &fixture) const {
  return !this->operator==(fixture);
}

unsigned long Fixture::maxActiveDuration() const {
  unsigned long max = 0;
  for (int sensor = SENSOR_MIN; sensor <= SENSOR_MAX; sensor++) {
    if (SENSOR_ACTIVE_DURATIONS[sensor] > max) {
      max = SENSOR_ACTIVE_DURATIONS[sensor];
    }
  }
  return max;
}

/**
 *  Get the initial status of sensors.
 *
 *  Delay a little bit longer than the max active duration to be safe.
 */
void Fixture::getInitSensorStatus() {
  updateSensorStatus();
  delay(maxActiveDuration() + 100);
  updateSensorStatus();
}

/**
 *  Enable the motor and wait for the hardware to become stable.
 */
void Fixture::start() {
  // Set the baud rate for Programming Port and Native USB Port.
  Serial.begin(SERIAL_BAUD_RATE);
  SerialUSB.begin(SERIAL_BAUD_RATE);

  // For safety, the motor should always be enabled to prevent from falling down
  enableMotor();

  // Delay for a while so that the sensors could begin functioning.
  delay(WARM_UP_WAIT);

  // Get the initial status of sensors.
  getInitSensorStatus();
}

/**
 * Enables the motor.
 *
 * Note: if the motor is disabled, the probe will fall to the ground as a
 *       free-falling object. This is rather dangerous since the probe is
 *       very heavy. Hence, the counter-function disableMotor() is not provided.
 */
void Fixture::enableMotor() {
  digitalWrite(pinMotorEn, LOW);
  motorEn_ = LOW;
}

/**
 * Convert a sensor enumerator to its corresponding pin number in Arduino DUE.
 *
 * The sensor value begins at 0 while the corresponding pin number begins at 2.
 */
int Fixture::getPin(enum Sensors sensor) const {
  return (sensor + pinJumper);
}

/**
 * Has the sensor value been active long enough?
 * SENSOR_ACTIVE_DURATIONS are used to prevent noise.
 */
bool Fixture::checkSensorValue(enum Sensors sensor) {
  unsigned long activeTime = SENSOR_ACTIVE_TIMES[sensor];
  unsigned long duration = activeTime > 0 ? millis() - activeTime : 0;
  return (duration > SENSOR_ACTIVE_DURATIONS[sensor]);
}

/**
 * Check if the sensors are active. Update the active times accordingly.
 */
void Fixture::updateSensorStatus() {
  for (int sensor = SENSOR_MIN; sensor <= SENSOR_MAX; sensor++) {
    if (digitalRead(getPin((enum Sensors) sensor)) ==
        SENSOR_ACTIVE_VALUES[sensor]) {
      if (SENSOR_ACTIVE_TIMES[sensor] == 0) {
        SENSOR_ACTIVE_TIMES[sensor] = millis();
      }
    } else {
      if (SENSOR_ACTIVE_TIMES[sensor] > 0) {
        SENSOR_ACTIVE_TIMES[sensor] = 0;
      }
    }
  }

  checkJumper();
  buttonDebug_ = checkSensorValue(BUTTON_DEBUG);
  sensorExtremeUp_ = checkSensorValue(SENSOR_EXTREME_UP);
  sensorUp_ = checkSensorValue(SENSOR_UP);
  sensorDown_ = checkSensorValue(SENSOR_DOWN);
  sensorSafety_ = checkSensorValue(SENSOR_SAFETY);
}

/**
 * Is the pinSensorExtremeUp detected?
 */
bool Fixture::isSensorExtremeUp() {
  return sensorExtremeUp_;
}

/**
 * Is the pinSensorUp or pinSensorExtremeUp detected?
 */
bool Fixture::isSensorUp() {
  return (sensorUp_ || sensorExtremeUp_);
}

/**
 * Is the pinSensorDown detected?
 */
bool Fixture::isSensorDown() {
  return sensorDown_;
}

/**
 * Is the pinSensorSafety triggered? (which indicates an emergency)
 */
bool Fixture::isSensorSafety() {
  return sensorSafety_;
}

/**
 * Is the debug button pressed?
 */
bool Fixture::isDebugPressed() {
  return buttonDebug_;
}

/**
 * Check if the jumper is set.
 */
void Fixture::checkJumper() {
  // In the factory, we would like to use the debug button anyway.
  // It might be a hassle for a tester if they need to check the jumper
  // to determine if the debug button is enabled.
  bool CHECK_JUMPER = false;
  jumper_ = CHECK_JUMPER ? checkSensorValue(JUMPER) : true;
}

/**
 * Is the probe in one of the stop states?
 */
bool Fixture::isInStopState() const {
  return (state_ == stateStopUp || state_ == stateStopDown ||
          state_ == stateEmergencyStop);
}

/**
 * Set the motor to the new pwm frequency.
 */
void Fixture::setSpeed(unsigned int pwmFrequency) {
  if (pwmFrequency_ != pwmFrequency) {
    pwmFrequency_ = pwmFrequency;
    PWMC_ConfigureClocks(pwmFrequency_ * PWM_MAX_DUTY_CYCLE, 0, VARIANT_MCK);
  }
}

/**
 * Locks the motor.
 * Set PWM duty cycle on pinMotorStep to 0. The motor stops rotating this way.
 */
void Fixture::lockMotor() {
  analogWrite(pinMotorStep, 0);
  motorDutyCycle_ = false;
}

/**
 * Unlocks the motor.
 * The motor must be unlocked before it can rotate.
 * Set PWM duty cycle on pinMotorStep to 128 (half duty).
 */
void Fixture::unlockMotor() {
  analogWrite(pinMotorStep, 128);
  motorDutyCycle_ = true;
  digitalWrite(pinMotorLock, HIGH);
  motorLock_ = HIGH;
}

/**
 * Drive the probe.
 */
void Fixture::driveProbe(const char state, const int pwmFrequency,
                         const bool direction) {
  state_ = state;
  setSpeed(pwmFrequency);
  setMotorDirection(direction);
  unlockMotor();
}

/**
 * Perform some actions when the motor reaches the UP/DOWN end position.
 */
void Fixture::stopProbe(char state) {
  state_ = state;
  reset_count();
  lockMotor();
}

/**
 * Sets the motor direction.
 */
void Fixture::setMotorDirection(bool direction) {
  digitalWrite(pinMotorDir, direction);
  motorDir_ = direction;
}

/**
 * Get the host operation command from the programming port.
 */
char Fixture::getCmdByProgrammingPort() const {
  return (Serial.available() ? Serial.read() : NULL);
}

/**
 * Send the returned code to the host in response to the host operation command.
 */
void Fixture::sendResponseByProgrammingPort(char ret_code) const {
  Serial.write(ret_code);
}

/**
 * Get a debug command from the native USB port.
 */
char Fixture::getCmdByNativeUSBPort() const {
  return (SerialUSB.available() ? SerialUSB.read() : NULL);
}

/**
 * Send the fixture's state vector through the native USB port.
 * This information is for debugging purpose.
 */
void Fixture::sendStateVectorByNativeUSBPort(Fixture &fixture) const {
  SerialUSB.print("<");
  SerialUSB.print(state_);
  SerialUSB.print(jumper_);
  SerialUSB.print(buttonDebug_);
  SerialUSB.print(sensorExtremeUp_);
  SerialUSB.print(sensorUp_);
  SerialUSB.print(sensorDown_);
  SerialUSB.print(sensorSafety_);
  SerialUSB.print(motorDir_);
  SerialUSB.print(motorEn_);
  SerialUSB.print(motorLock_);
  SerialUSB.print(motorDutyCycle_);
  SerialUSB.print('.');
  SerialUSB.print(pwmFrequency_);
  SerialUSB.print('.');
  SerialUSB.print(count_);
  SerialUSB.print(">");
}
