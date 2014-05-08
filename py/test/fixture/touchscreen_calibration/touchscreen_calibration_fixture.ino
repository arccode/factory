// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * The arduino firmware which controls the touchscreen fixture.
 */


const int jumper = 2;
const int debug = 3;

// sensor pins
const int sensorExtremeUp = 4;
const int sensorUp = 5;
const int sensorDown = 6;
const int sensorSafety = 7;

// pins to control the motor
const int motorStep = 8;
const int motorDir = 9;
const int motorEn = 10;
const int motorLock = 11;

// Actual test fixture active values
const boolean SENSOR_EXTREME_UP_ACTIVE_VALUE = HIGH;
const boolean SENSOR_UP_ACTIVE_VALUE = HIGH;
const boolean SENSOR_DOWN_ACTIVE_VALUE = HIGH;
const boolean SENSOR_SAFETY_TRIGGERED_VALUE = LOW;
const boolean DEBUG_PRESSED_ACTIVE_VALUE = HIGH;
const boolean JUMPER_ACTIVE_VALUE = HIGH;

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

// commands from the host
const char cmdDown = 'd';
const char cmdUp = 'u';
const char cmdState = 's';

// Define SUCCESS and ERROR codes.
const char SUCCESS = '0';
const char ERROR = '1';

// The delay interval between two consecutive sensing.
const int SENSOR_DELAY_INTERVAL = 10;

// The higher the value, the slower the motor speed.
const int FAST_PWM_FREQUENCY = 6000;
const int SLOW_PWM_FREQUENCY = 2000;

// The values set on the motorDir digital pin to control the motor direction.
const bool MOTOR_DIR_UP = LOW;
const bool MOTOR_DIR_DOWN = HIGH;

// The motor is supposed to travel this fast distance and then slow down.
const unsigned int DISTANCE_TO_SLOW_DOWN = 256000 * 5 / 6;

const int WARM_UP_WAIT = 2000;
const int SERIAL_BAUD_RATE = 9600;

char state = stateInit;
char command = NULL;
boolean flagJumper = false;
unsigned int count = 0;
unsigned int pwm_frequency = SLOW_PWM_FREQUENCY;


/**
 * The setup routine runs once on power on or reset.
 */
void setup() {
  // Set the baud rate
  Serial.begin(SERIAL_BAUD_RATE);

  // Initialize the input debug pins and sensor pins
  pinMode(jumper, INPUT);
  pinMode(debug, INPUT);
  pinMode(sensorExtremeUp, INPUT);
  pinMode(sensorUp, INPUT);
  pinMode(sensorDown, INPUT);
  pinMode(sensorSafety, INPUT);

  // Initialize the output pins for the motor control
  // Note: there is no need to configure motorStep as OUTPUT
  //       when driving it with PWM.
  pinMode(motorDir, OUTPUT);
  pinMode(motorEn, OUTPUT);
  pinMode(motorLock, OUTPUT);

  // Important: the motor must be always enabled. Otherwise, the probe will
  //            fall to the ground like a free-falling object.
  enableMotor();

  // Wait for the hardware to become stable.
  delay(WARM_UP_WAIT);

  // Ensure that the probe parks at the UP position initially.
  if (isSensorUp()) {
    StopProbe(stateInit);
  } else {
    driveProbe(stateGoingUp, FAST_PWM_FREQUENCY, MOTOR_DIR_UP);
  }

  // If the jumper is set, an operator can press debug button to control the
  // probe to go up/down.
  flagJumper = isJumperSet();
}

/**
 * The loop polls the host command continuously and invokes the state machine.
 */
void loop() {
  // Responds to the host command.
  command = Serial.available() ? Serial.read() : NULL;
  stateControl(command);
}

/**
 * The state machine responds to the host command and the sensors.
 */
void stateControl(char command) {
  // Checks if there is an emergency stop.
  if (isSensorSafety()) {
    handleEmergencyStop();
  } else if (state == stateEmergencyStop) {
    handleDebugPressed();
  } else if (state == stateGoingUpAfterEmergency) {
    gotoUpPosition();
  } else {
    // Responds to the host command.
    if ((command == cmdDown || (flagJumper && isDebugPressed())) &&
        (state == stateInit || state == stateStopUp)) {
      // Takes the go Down command only when the probe is in its Up position.
      driveProbe(stateGoingDown, FAST_PWM_FREQUENCY, MOTOR_DIR_DOWN);
    } else if ((command == cmdUp || (flagJumper && isDebugPressed())) &&
               (state == stateStopDown)) {
      // Takes the go Up command only when the probe is in its Down position.
      driveProbe(stateGoingUp, FAST_PWM_FREQUENCY, MOTOR_DIR_UP);
    } else if (command != cmdState && command != NULL) {
      sendResponse(ERROR);
    }
    driveMotorTowardEndPosition();
  }

  // Check the jumper only in a stop state as the operator is not supposed
  // to change the jumper when the motor is moving.
  // Detecting the jumper condition here in addition to when the arduino is
  // booted up is useful so that the operator does not need to unplug the
  // USB calbe from the host to reset the arduino.
  if (isInStopState())
    flagJumper = isJumperSet();

  if (command == cmdState)
    sendResponse(state);
}

/**
 * Drive the motor in its direction until reaching the UP/DOWN end position.
 */
void driveMotorTowardEndPosition() {
  if (state == stateGoingDown || state == stateGoingUp) {
    count++;
    if (state == stateGoingDown && isSensorDown()) {
      StopProbe(stateStopDown);
      sendResponse(state);
    } else if (state == stateGoingUp && isSensorUp()) {
      StopProbe(stateStopUp);
      sendResponse(state);
    } else {
      adjustSpeed();
    }
  }
}

/**
 * Sends the returned code and message to the host.
 */
void sendResponse(char ret_code) {
  Serial.write(ret_code);
}

/**
 * Adjust speed according to the probe position.
 */
void adjustSpeed() {
  if (isFast() && (count >= DISTANCE_TO_SLOW_DOWN)) {
    setSpeed(SLOW_PWM_FREQUENCY);
  }
}

/**
 * Is the motor in fast speed?
 */
bool isFast() {
  return (pwm_frequency == FAST_PWM_FREQUENCY);
}

void setSpeed(unsigned int new_pwm_frequency) {
  if (new_pwm_frequency != pwm_frequency) {
    pwm_frequency = new_pwm_frequency;
    PWMC_ConfigureClocks(pwm_frequency * PWM_MAX_DUTY_CYCLE, 0, VARIANT_MCK);
  }
}

/**
 * Is the sensor value detected twice? (Check twice to prevent any noise.)
 */
boolean checkSensorValueTwice(const int sensor, int value) {
  if (digitalRead(sensor) != value) {
    return false;
  } else {
    delay(SENSOR_DELAY_INTERVAL);
    return (digitalRead(sensor) == value);
  }
}

/**
 * Is the sensorExtremeUp detected?
 */
boolean isSensorExtremeUp() {
  return checkSensorValueTwice(sensorExtremeUp, SENSOR_EXTREME_UP_ACTIVE_VALUE);
}

/**
 * Is the sensorUp or sensorExtremeUp detected?
 */
boolean isSensorUp() {
  return (isSensorExtremeUp() ||
          checkSensorValueTwice(sensorUp, SENSOR_UP_ACTIVE_VALUE));
}

/**
 * Is the sensorDown detected?
 */
boolean isSensorDown() {
  return checkSensorValueTwice(sensorDown, SENSOR_DOWN_ACTIVE_VALUE);
}

/**
 * Is the sensorSafety triggered? (which indicates an emergency)
 */
boolean isSensorSafety() {
  return checkSensorValueTwice(sensorSafety, SENSOR_SAFETY_TRIGGERED_VALUE);
}

/**
 * Is the debug button pressed?
 */
boolean isDebugPressed() {
  return checkSensorValueTwice(debug, DEBUG_PRESSED_ACTIVE_VALUE);
}

/**
 * Is the jumper set?
 */
boolean isJumperSet() {
  return checkSensorValueTwice(jumper, JUMPER_ACTIVE_VALUE);
}

/**
 * Is the probe in one of the stop states?
 */
boolean isInStopState() {
  return (state == stateStopUp || state == stateStopDown ||
          state == stateEmergencyStop);
}

/**
 * Sets the motor direction to go down.
 */
void setMotorDirectionDown() {
  digitalWrite(motorDir, HIGH);
}

/**
 * Sets the motor direction to go up.
 */
void setMotorDirectionUp() {
  digitalWrite(motorDir, LOW);
}

/**
 * Sets the motor direction.
 */
void setMotorDirection(bool direction) {
  digitalWrite(motorDir, direction);
}

/**
 * Enables the motor.
 *
 * Note: if the motor is disabled, the probe will fall to the ground as a
 *       free-falling object. In most cases, this is dangerous as the probe is
 *       very heavy. Hence, the counter function disableMotor() is not provided.
 */
void enableMotor() {
  digitalWrite(motorEn, LOW);
}

/**
 * Emergency stop due to sensorSafety being triggered.
 */
void handleEmergencyStop() {
  if (isSensorUp()) {
    state = stateStopUp;
  } else {
    StopProbe(stateEmergencyStop);
  }
}

/**
 * Once the debug button is pressed after an emergency stop, prepare to drive
 * the probe back to the UP position.
 */
void handleDebugPressed() {
  if (isDebugPressed()) {
    driveProbe(stateGoingUpAfterEmergency, SLOW_PWM_FREQUENCY, MOTOR_DIR_UP);
  }
}

/**
 * Drive the probe.
 */
void driveProbe(char new_state, const int new_pwm_frequency,
                const bool direction) {
  state = new_state;
  setSpeed(new_pwm_frequency);
  setMotorDirection(direction);
  unlockMotor();
}

/**
 * Perform some actions when the motor reaches the UP/DOWN end position.
 */
void StopProbe(char newState) {
  state = newState;
  count = 0;
  lockMotor();
}

/**
 * The probe goes to the UP position.
 */
void gotoUpPosition() {
  if (isSensorUp())
    StopProbe(stateStopUp);
}

/**
 * Locks the motor.
 */
void lockMotor() {
  // Set PWM duty cycle on motorStep to 0. The motor stops rotating this way.
  analogWrite(motorStep, 0);
}

/**
 * Unlocks the motor. The motor must be unlocked before it can rotate.
 */
void unlockMotor() {
  // Set PWM duty cycle on motorStep to 128 (half duty).
  analogWrite(motorStep, 128);
  digitalWrite(motorLock, HIGH);
}
