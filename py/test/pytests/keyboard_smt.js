// Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for keyboard SMT test.
 * @constructor
 * @param {Array} keycodeSequence
 * @param {bool} debug
 */
keyboardSmtTest = function(keycodeSequence, debug) {
  this.expectedKeycodeSequence = keycodeSequence;
  this.receivedKeycodeSequence = [];
  this.debug = debug
};

/**
 * Initializes keyboard SMT test UI.
 */
keyboardSmtTest.prototype.init = function() {
  document.getElementById("expected-sequence").innerHTML =
      this.expectedKeycodeSequence.join(" ");
};

/**
 * Checks if the received keycode matches and highlights the mached ones.
 *
 * If keycode mismatches, fails the test. If all expected keycodes are matched,
 * passes it.
 *
 * @param {int} keycode
 */
keyboardSmtTest.prototype.markKeyup = function(keycode) {
  this.receivedKeycodeSequence.push(keycode);
  if (this.debug) {
    // Update UI.
    document.getElementById("matched-sequence").innerHTML =
        this.receivedKeycodeSequence.join(" ") + " ";
    document.getElementById("expected-sequence").innerHtml =
        this.expectedKeycodeSequence.join(" ");
  } else {
    var numReceivedKeycode = this.receivedKeycodeSequence.length;
    var numExpectedKeycode = this.expectedKeycodeSequence.length;
    if (numReceivedKeycode > numExpectedKeycode ||
        keycode != this.expectedKeycodeSequence[numReceivedKeycode - 1]) {
      this.failTest('Keycode sequence mismatches.');
    }

    // Update UI.
    document.getElementById("matched-sequence").innerHTML =
        this.expectedKeycodeSequence.slice(0, numReceivedKeycode).join(" ")
        + " ";
    document.getElementById("expected-sequence").innerHTML =
        this.expectedKeycodeSequence.slice(numReceivedKeycode,
                                           numExpectedKeycode).join(" ");

    // All keycodes are matched. Pass the test.
    if (numReceivedKeycode == numExpectedKeycode) {
      window.test.pass();
    }
  }
};


/**
 * Fails the test and prints out all the failed keys.
 * @param {str} reason
 */
keyboardSmtTest.prototype.failTest = function(reason) {
  window.test.fail(
      [reason, "expect:", this.expectedKeycodeSequence.join(","),
       "actual:", this.receivedKeycodeSequence.join(",")].join(" "));
};

/**
 * Creates a keyboard test and runs it.
 * @param {Array} keycodeSequence
 * @param {bool} debug
 */
function setUpKeyboardTest(keycodeSequence, debug) {
  window.keyboardSmtTest = new keyboardSmtTest(keycodeSequence, debug);
  window.keyboardSmtTest.init();
}

/**
 * Marks a key as keyup.
 * @param {int} keycode
 */
function markKeyup(keycode) {
  window.keyboardSmtTest.markKeyup(keycode);
}

/**
 * Fails the test.
 * @param {str} reason
 */
function failTest(reason) {
  window.keyboardSmtTest.failTest(reason);
}
