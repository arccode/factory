// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * The arduino firmware which controls the touchscreen fixture.
 */


// debug pins
// TODO(josephsih): add logic about jump later for the manual debug mode.
const int jump = 2;
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
const int HALF_PULSE_WIDTH = 80;

const int WARM_UP_WAIT = 2000;
const int SERIAL_BAUD_RATE = 9600;

char state = stateInit;
char command = NULL;


/**
 * The setup routine runs once on power on or reset.
 */
void setup() {
  // Set the baud rate
  Serial.begin(SERIAL_BAUD_RATE);

  // Initialize the input debug pins and sensor pins
  pinMode(jump, INPUT);
  pinMode(debug, INPUT);
  pinMode(sensorExtremeUp, INPUT);
  pinMode(sensorUp, INPUT);
  pinMode(sensorDown, INPUT);
  pinMode(sensorSafety, INPUT);

  // Initialize the output pins for the motor control
  pinMode(motorStep, OUTPUT);
  pinMode(motorDir, OUTPUT);
  pinMode(motorEn, OUTPUT);
  pinMode(motorLock, OUTPUT);

  // Important: the motor must be always enabled. Otherwise, the probe will
  //            fall to the ground like a free-falling object.
  enableMotor();

  // Wait for the hardware to become stable.
  delay(WARM_UP_WAIT);

  // Go to the UP position initially when powered on.
  if (!isSensorUp()) {
    state = stateGoingUp;
    setMotorDirectionUp();
  }

  // Unlock the motor so that it could rotate.
  unlockMotor();
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
    if ((command == cmdDown) &&
        (state == stateInit || state == stateStopUp)) {
      // Takes the go Down command only when the probe is in its Up position.
      state = stateGoingDown;
      setMotorDirectionDown();
    } else if ((command == cmdUp) && (state == stateStopDown)) {
      // Takes the go Up command only when the probe is in its Down position.
      state = stateGoingUp;
      setMotorDirectionUp();
    } else if (command != cmdState && command != NULL) {
      sendResponse(ERROR);
    }

    // Responds to the status of sensors.
    if (state == stateGoingDown) {
      if (isSensorDown()) {
        state = stateStopDown;
        sendResponse(state);
      } else {
        driveMotorOneStep();
      }
    } else if (state == stateGoingUp) {
      if (isSensorUp()) {
        state = stateStopUp;
        sendResponse(state);
      } else {
        driveMotorOneStep();
      }
    }
  }

  if (command == cmdState)
    sendResponse(state);
}

/**
 * Sends the returned code and message to the host.
 */
void sendResponse(char ret_code) {
  Serial.write(ret_code);
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
 * Is the debug pin pressed?
 */
boolean isDebugPressed() {
  return checkSensorValueTwice(debug, DEBUG_PRESSED_ACTIVE_VALUE);
}

/**
 * Drive the motor one step.
 */
void driveMotorOneStep() {
  digitalWrite(motorStep, LOW);
  delayMicroseconds(HALF_PULSE_WIDTH);
  digitalWrite(motorStep, HIGH);
  delayMicroseconds(HALF_PULSE_WIDTH);
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
    state = stateEmergencyStop;
    setMotorDirectionUp();
  }
}

/**
 * Once the debug button is pressed after an emergency stop, prepare to drive
 * the probe back to the UP position.
 */
void handleDebugPressed() {
  if (isDebugPressed())
    state = stateGoingUpAfterEmergency;
}

/**
 * The probe goes to the UP position.
 */
void gotoUpPosition() {
  if (isSensorUp()) {
    state = stateStopUp;
  } else {
    driveMotorOneStep();
  }
}

/**
 * Locks the motor.
 */
void lockMotor() {
  digitalWrite(motorLock, LOW);
}

/**
 * Unlocks the motor. The motor must be unlocked before it can rotate.
 */
void unlockMotor() {
  digitalWrite(motorLock, HIGH);
}
