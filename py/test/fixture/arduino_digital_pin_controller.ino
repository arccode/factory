// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * Arduino digital pin controller that sets pins' states depending on the
 * commands read from the serial.
 *
 * At first, all pins are LOW. The command is a 2 bytes sequence, the first one
 * indicates the pin number, and the second on is either L or H. L means LOW
 * and H means HIGH.
 */


// Arduino UNO has 14 pins, others like DUE have more. But there's no way to
// get the pin count from Arduino's API. So hard coded here.
const int pinCount = 14;

// When establishing the connection, the ArduinoController will send '1' '2'
// '3' for hanshaking. This variable is false at first, and will be true after
// that.
bool handShaked = false;


/**
 * Initializes the serial and all pins to LOW.
 */
void setup()
{
  Serial.begin(9600);
  for (int i = 0; i < pinCount; ++i) {
    pinMode(i, OUTPUT);
    digitalWrite(i, LOW);
  }
}

/**
 * Processes the commands forever. See the firmware description at the top of
 * this file for more info about the format of commands.
 */
void loop()
{
  if (!handShaked) {
    if (Serial.available() <= 0)
      return;
    int c = Serial.read();
    Serial.write(c);
    if (c == 3)
      handShaked = true;
  } else {
    if (Serial.available() < 2)
      return;

    int pin = Serial.read();
    char level = Serial.read();
    if ((pin < 2 || pin >= pinCount) || (level != 'H' && level != 'L')) {
      Serial.println("Unrecognized command.");
    } else {
      if (level == 'H')
        digitalWrite(pin, HIGH);
      else
        digitalWrite(pin, LOW);
      // Echo the command.
      Serial.write(pin);
      Serial.write(level);
    }
  }
}
