// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/*
 * The fixture class which maintains its internal states and performs
 * basic actions.
 */


#ifndef Fixture_h
#define Fixture_h


// Possible main state of the test fixture.
extern const char stateInit;
extern const char stateGoingDown;
extern const char stateGoingUp;
extern const char stateStopDown;
extern const char stateStopUp;
extern const char stateEmergencyStop;
extern const char stateGoingUpAfterEmergency;

extern const int FAST_PWM_FREQUENCY;
extern const int SLOW_PWM_FREQUENCY;

extern const bool MOTOR_DIR_UP;
extern const bool MOTOR_DIR_DOWN;


class Fixture {
  public:
    // Enumeration of all the jumper, the button, and the four sensors.
    enum Sensors {JUMPER = 0,
                  BUTTON_DEBUG,
                  SENSOR_EXTREME_UP,
                  SENSOR_UP,
                  SENSOR_DOWN,
                  SENSOR_SAFETY,
    };
    static const enum Sensors SENSOR_MIN = JUMPER;
    static const enum Sensors SENSOR_MAX = SENSOR_SAFETY;

    // A default constructor which configures pins in addition to initializing
    // its data members.
    Fixture();
    // A constructor which initializes its data members only.
    Fixture(const Fixture &fixture) { this->operator=(fixture); };

    Fixture& operator=(const Fixture &fixture);
    bool operator==(const Fixture &fixture) const;
    bool operator!=(const Fixture &fixture) const;
    void start();
    void enableMotor();
    void updateSensorStatus();
    bool isSensorExtremeUp();
    bool isSensorUp();
    bool isSensorDown();
    bool isSensorSafety();
    bool isDebugPressed();
    void checkJumper();
    bool isInStopState() const;
    void setSpeed(unsigned int pwmFrequency);
    void lockMotor();
    void unlockMotor();
    void driveProbe(const char state, const int pwmFrequency,
                    const bool direction);
    void stopProbe(char state);
    void setMotorDirection(bool direction);

    // Accessors and mutator below
    char state() const { return state_; }
    void set_state(char state) { state_ = state; }
    bool jumper() const { return jumper_; }
    unsigned int count() const { return count_; }
    void inc_count() { count_++; }
    void reset_count() { count_ = 0; }

    // communication
    char getCmdByProgrammingPort() const;
    void sendResponseByProgrammingPort(char ret_code) const;
    char getCmdByNativeUSBPort() const;
    void sendStateVectorByNativeUSBPort(Fixture &fixture) const;

  private:
    bool checkSensorValue(enum Sensors sensor);
    int getPin(enum Sensors sensor) const;
    unsigned long maxActiveDuration() const;
    void getInitSensorStatus();

    // Fixture's state vector
    // the main state
    char state_;

    // the motor rotation count
    unsigned int count_;
    // the pwm frequency, either fast or slow
    unsigned int pwmFrequency_;

    // Sensor properties
    // The jumper used to determine if the fixture is in debug mode.
    bool jumper_;
    // The is the DEBUG button on the left side of the test fixture.
    bool buttonDebug_;
    // The highest sensor.
    // The probe should not reach this height in a normal situation.
    bool sensorExtremeUp_;
    // This sensor indicates if the probe has reached the UP position.
    // The sensor a bit lower than the highest sensor.
    bool sensorUp_;
    // This sensor indicates if the probe has reached the DOWN position.
    bool sensorDown_;
    // This sensor is triggered whenever there is an object (usually a hand)
    // intruding into the test fixture.
    bool sensorSafety_;

    // Motor properties
    // The motor rotating direction, either up or down
    bool motorDir_;
    // The motor should be always enabled to prevent from falling down.
    bool motorEn_;
    // Should unlock the motor before starting to rotate.
    bool motorLock_;
    // the motor duty cycle, could be either 0 or half duty cycle.
    bool motorDutyCycle_;
};

#endif
