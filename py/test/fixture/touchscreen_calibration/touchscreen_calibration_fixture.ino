// Copyright 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * The arduino firmware which controls the touchscreen test fixture.
 */

#include <DueTimer.h>
#include "Fixture.h"


// Commands from the host
// Command the fixture to go down.
const char cmdDown = 'd';
// Command the fixture to go up.
const char cmdUp = 'u';
// Query the fixture state.
const char cmdState = 's';
// Query the motor rotation count.
const char cmdCount = 'c';
// Query the PWM speed.
const char cmdPwm = 'p';

// Define SUCCESS and ERROR.
const char SUCCESS = '0';
const char ERROR = '1';

// The pwm frequency: the higher the value, the faster the motor speed.
const int FAST_PWM_FREQUENCY = 6000;
const int SLOW_PWM_FREQUENCY = 2000;

// When either of the following two conditions is met, the probe slows down.
// (1) count is greater than DISTANCE_TO_SLOW_DOWN, or
// (2) the elapsed time is greater than TIME_TO_SLOW_DOWN.
//
// The two parameters are derived with experiments.
// DISTANCE_TO_SLOW_DOWN: this value is affected by FAST_PWM_FREQUENCY and
//                        how much time is consumed per iteration in loop().
// TIME_TO_SLOW_DOWN : this value is affected by FAST_PWM_FREQUENCY only.
const unsigned int DISTANCE_TO_SLOW_DOWN = 256000 * 5 / 6; // in loop count
const unsigned int TIME_TO_SLOW_DOWN = 3300000;            // in micro-seconds

// the pwm frequency, either fast or slow
volatile unsigned int pwmFrequency = SLOW_PWM_FREQUENCY;

// Get a timer interrupt to slow down the probe.
DueTimer speedTimer = Timer.getAvailable().attachInterrupt(speedTimerISR);

// The command delivered by the host.
char command = NULL;

// Maintain current and last fixture properties.
Fixture fixture = Fixture();
Fixture lastFixture = Fixture(fixture);


/**
 * Initialize the test fixture to a known state.
 */
void setup() {
  // Enable the motor and wait for the hardware to become stable.
  fixture.start();

  // Ensure that the probe parks at the UP position initially.
  if (fixture.isSensorUp()) {
    stopProbe(stateInit);
    setSpeed(FAST_PWM_FREQUENCY);
  } else {
    // If the probe does not park at the DOWN position, use a slow speed.
    // Otherwise, there is no way to know when to slow down.
    driveProbe(stateGoingUp,
               fixture.isSensorDown() ? FAST_PWM_FREQUENCY : SLOW_PWM_FREQUENCY,
               MOTOR_DIR_UP);
  }

  // If the jumper is set, an operator can press debug button to control the
  // probe to go up/down.
  fixture.checkJumper();

  // Send the fixture's state vector to the host.
  sendFixtureStateVector();
}

/**
 * The loop polls the host command continuously and processes the command.
 */
void loop() {
  // Responds to the host command.
  command = fixture.getCmdByProgrammingPort();
  stateControl(command);
  sendFixtureStateVector();
  lastFixture = fixture;
}

/**
 * Send the fixture's state vector to the host via the native USB port whenever
 * (1) there is a state change or
 * (2) when the fixture receives a state query command (for debug)
 *     from the host.
 */
void sendFixtureStateVector() {
  if ((fixture != lastFixture) || fixture.getCmdByNativeUSBPort() == cmdState) {
    fixture.sendStateVectorByNativeUSBPort(fixture);
  }
}

/**
 * The state machine responds to the host command and the sensors.
 */
void stateControl(char command) {
  // Check all of the sensors continuously and update the status.
  fixture.updateSensorStatus();

  // Checks if there is an emergency stop.
  if (fixture.isSensorSafety()) {
    handleEmergencyStop();
  } else if (fixture.state() == stateEmergencyStop) {
    handleDebugPressed();
  } else if (fixture.state() == stateGoingUpAfterEmergency) {
    gotoUpPosition();
  } else {
    // Responds to the host command.
    if ((command == cmdDown ||
         (fixture.jumper() && fixture.isDebugPressed())) &&
        (fixture.state() == stateInit || fixture.state() == stateStopUp)) {
      // Takes the go Down command only when the probe is in its Up position.
      driveProbe(stateGoingDown, FAST_PWM_FREQUENCY, MOTOR_DIR_DOWN);
    } else if ((command == cmdUp ||
                (fixture.jumper() && fixture.isDebugPressed())) &&
               (fixture.state() == stateStopDown)) {
      // Takes the go Up command only when the probe is in its Down position.
      driveProbe(stateGoingUp, FAST_PWM_FREQUENCY, MOTOR_DIR_UP);
    } else if (command != cmdState && command != NULL) {
      fixture.sendResponseByProgrammingPort(ERROR);
    }
    driveMotorTowardEndPosition();
  }

  // Check the jumper only in a stop state as the operator is not supposed
  // to change the jumper when the motor is moving.
  // Detecting the jumper condition here in addition to when the arduino is
  // booted up is useful so that the operator does not need to unplug the
  // USB cable from the host to reset the arduino.
  if (fixture.isInStopState())
    fixture.checkJumper();

  if (command == cmdState)
    fixture.sendResponseByProgrammingPort(fixture.state());
}

/**
 * Drive the motor in its direction until reaching the UP/DOWN end position.
 */
void driveMotorTowardEndPosition() {
  if (fixture.state() == stateGoingDown || fixture.state() == stateGoingUp) {
    fixture.inc_count();
    if (fixture.state() == stateGoingDown && fixture.isSensorDown()) {
      stopProbe(stateStopDown);
      fixture.sendResponseByProgrammingPort(fixture.state());
    } else if (fixture.state() == stateGoingUp && fixture.isSensorUp()) {
      stopProbe(stateStopUp);
      fixture.sendResponseByProgrammingPort(fixture.state());
    } else {
      adjustSpeedByCount();
    }
  }
}

/**
 * Emergency stop due to sensor safety pin being triggered.
 */
void handleEmergencyStop() {
  if (fixture.isSensorUp()) {
    fixture.set_state(stateStopUp);
  } else {
    stopProbe(stateEmergencyStop);
  }
}

/**
 * Once the debug button is pressed after an emergency stop, prepare to drive
 * the probe back to the UP position.
 */
void handleDebugPressed() {
  if (fixture.isDebugPressed()) {
    driveProbe(stateGoingUpAfterEmergency, SLOW_PWM_FREQUENCY, MOTOR_DIR_UP);
  }
}

/**
 * The probe goes to the UP position.
 */
void gotoUpPosition() {
  if (fixture.isSensorUp())
    stopProbe(stateStopUp);
}

/**
 * A wraper of Fixutre::driveProbe with timer start.
 */
void driveProbe(const char state, const int newPwmFrequency,
                const bool direction) {
  speedTimer.start(TIME_TO_SLOW_DOWN);
  pwmFrequency = newPwmFrequency,
  fixture.driveProbe(state, pwmFrequency, direction);
}

/**
 * A wraper of Fixutre::stopProbe with timer stop.
 */
void stopProbe(const char state) {
  fixture.stopProbe(state);
  speedTimer.stop();
}


/**
 * Adjust the pwm frequency speed according to count, i.e., the probe position.
 */
void adjustSpeedByCount() {
  if ((pwmFrequency == FAST_PWM_FREQUENCY) &&
      (fixture.count() >= DISTANCE_TO_SLOW_DOWN)) {
    setSpeed(SLOW_PWM_FREQUENCY);
  }
}

/**
 * The ISR to slow down the probe when the timer goes off.
 */
void speedTimerISR() {
  setSpeed(SLOW_PWM_FREQUENCY);
  speedTimer.stop();
}

/**
 * A simple wrapper of Fixture::setSpeed and pwmFrequency.
 */
void setSpeed(unsigned int newPwmFrequency) {
    pwmFrequency = newPwmFrequency;
    fixture.setSpeed(pwmFrequency);
}
