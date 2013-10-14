// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var image_data;

////////////////////////////////////////////////////////////
// Callables from Python
////////////////////////////////////////////////////////////

/**
 * Init entry for calibration of camera test fixture.
 */
function InitForCalibration() {
  document.getElementById("main_screen").hidden = false;
  button_style = document.getElementById("button_run_test").style.visibility =
      'hidden';
  document.getElementById("preview_image").hidden = false;
}

/**
 * Init entry for standalone camera lens shading test.
 */
function InitForLensShading() {
  document.getElementById("main_screen").hidden = false;
  button_style = document.getElementById("button_run_test").style.visibility =
      'hidden';
  document.getElementById("preview_image").hidden = false;
}

/**
 * Clears image data.
 */
function ClearImageData() {
  image_data = "";
}

/**
 * Appends data for camera_image. This function may be used multiple times to
 * send an image to JavaScript due to the limitation of message size.
 * @param {string} data Base64-encoded image data
 */
function AddImageData(data) {
  image_data += data;
}

/**
 * Updates the image display after AddImageData().
 * @param {string} image_id The HTML id of the image to update.
 */
function UpdateImage(image_id) {
  var element = document.getElementById(image_id);
  element.src = "data:image/jpeg;base64," + image_data;
}

/**
 * Updates the test status block.
 * @param {string} msg Status message.
 */
function UpdateTestStatus(msg) {
  var statusText = document.getElementById("test_status");
  statusText.innerHTML = msg;
}

////////////////////////////////////////////////////////////
// Event handlers
////////////////////////////////////////////////////////////

/**
 * When "Exit Test" button is clicked.
 */
function OnButtonExitTestClick() {
  test.sendTestEvent("exit_test_button_clicked", {});
}

////////////////////////////////////////////////////////////
// Internal methods
////////////////////////////////////////////////////////////

