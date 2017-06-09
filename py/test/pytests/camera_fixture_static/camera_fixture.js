// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Whether to input serial number manually by user.
var g_use_sn_input = false;

// Whether to load/store data on USB drive.
var g_use_usb = false;

// Whether the DUT should control fixture
var g_use_fxt = false;

// Whether the USB drive is loaded.
var g_is_usb_loaded = false;

// Whether fixture is loaded
var g_is_fxt_loaded = false;

// Whether the test is running or not. Because UI is running in background
// thread, we need to disable 'Start Test' button when the test is
// running. Otherwise, if user clicks the button twice quickly, the test will
// auto start twice.
var g_is_test_running = false;

// Incrementally loaded image data.
var g_image_data;

var label_usb_loaded = cros.factory.i18n.i18nLabel('USB LOADED');
var label_usb_unloaded = cros.factory.i18n.i18nLabel('USB UNLOADED');
var label_fxt_loaded = cros.factory.i18n.i18nLabel('Fixture CONNECTED');
var label_fxt_unloaded = cros.factory.i18n.i18nLabel('Fixture UNAVAILABLE');


////////////////////////////////////////////////////////////
// Callables from Python
////////////////////////////////////////////////////////////


/**
 * Init layout for calibration of camera test fixture.
 */
function InitForCalibration() {
  document.getElementById('main_screen').hidden = false;
  GetStartTestButton().style.visibility = 'hidden';
  document.getElementById('preview_image').hidden = false;
}


/**
 * Init layout for standalone camera lens shading test.
 */
function InitForLensShadingTest() {
  document.getElementById('main_screen').hidden = false;
  GetStartTestButton().style.visibility = 'hidden';
  document.getElementById('preview_image').hidden = false;
}


/**
 * Init layout for standalone QR Code test.
 */
function InitForQRCodeTest() {
  document.getElementById('main_screen').hidden = false;
  GetStartTestButton().style.visibility = 'hidden';
  document.getElementById('preview_image').hidden = false;
}


/**
 * Init layout for IQ test on light chamber.
 *
 * @param {string} data_method Data method defined in CameraFixture.ARGS[]
 * @param {boolean} control_chamber Whether or not DUT controls the chamber
 */
function InitForTest(data_method, control_chamber) {
  // Hide main test screen, and show prompt screen for USB drive or ethernet
  // dongle.

  if (control_chamber) {
    document.getElementById('fixture_status_panel').hidden = false;
    g_use_fxt = true;
  }

  if (data_method == 'Simple') {
    // do nothing
  } else if (data_method == 'USB') {
    document.getElementById('main_screen').hidden = true;
    document.getElementById('usb_status_panel').hidden = false;
    document.getElementById('prompt_usb').hidden = false;
    g_use_usb = true;
  } else if (data_method == 'Shopfloor') {
    document.getElementById('main_screen').hidden = true;
    document.getElementById('prompt_ethernet').hidden = false;
  } else {
    alert('Invalid data_method');
  }
}


/**
 * Shows main test screen for IQ test.
 *
 * @param {boolean} manual_sn_input Whether to input serial number manually.
 */
function ShowMainTestScreen(manual_sn_input) {
  var sn_status_panel = document.getElementById('sn_status_panel');
  var sn_input_box = GetSnInputBox();

  g_use_sn_input = manual_sn_input;

  if (manual_sn_input) {
    sn_status_panel.hidden = false;
    sn_input_box.disabled = false;
    sn_input_box.autofocus = true;
    sn_input_box.focus();
  }

  OnCheckButtonState();

  document.getElementById('main_screen').hidden = false;
  document.getElementById('prompt_usb').hidden = true;
  document.getElementById('prompt_ethernet').hidden = true;
}


/**
 * Clears image data.
 */
function ClearImageData() {
  g_image_data = '';
}


/**
 * Appends data for camera_image. This function may be used multiple times to
 * send an image to JavaScript due to the limitation of message size.
 * @param {string} data Base64-encoded image data
 */
function AddImageData(data) {
  g_image_data += data;
}


/**
 * Updates the image data after AddImageData() and show it.
 * @param {string} html_id The HTML id of the image to show.
 */
function UpdateAndShowImage(html_id) {
  var element = document.getElementById(html_id);
  element.src = 'data:image/jpeg;base64,' + g_image_data;

  /*
   * camera_image and analyzed_image both have 'position' = 'absolute' so that
   * they can overlap with each other.
   *
   * Align them to the center manually. This may show translation animation due
   * to -webkit-transition style, but it's okay.
   */
  if (html_id == 'camera_image' || html_id == 'analyzed_image') {
    element.style.marginTop = '-' + (element.height / 2) + 'px';
    element.style.marginLeft = '-' + (element.width / 2) + 'px';
  }

  element.hidden = false;
}


/**
 * Hides an image.
 * @param {string} html_id The HTML id of the image to hide.
 */
function HideImage(html_id) {
  document.getElementById(html_id).hidden = true;
}


/**
 * Updates a text label.
 * @param {string} msg Text.
 * @param {string} html_id The HTML id of the text label (usually a div block).
 */
function UpdateTextLabel(msg, html_id) {
  var element = document.getElementById(html_id);
  element.innerHTML = msg;
}


/**
 * Updates progress bar.
 * @param {string} progress Completion percentage.
 */
function UpdateProgressBar(progress) {
  var pBar = document.getElementById('progress_bar');
  pBar.style.width = progress;
}


/**
 * Updates USB load status.
 * @param {boolean} is_loaded Whether USB drive is loaded.
 */
function UpdateUSBStatus(is_loaded) {
  g_is_usb_loaded = is_loaded;

  var usb_status = document.getElementById('usb_status');
  var usb_status_text = document.getElementById('usb_status_text');

  if (is_loaded) {
    goog.dom.safe.setInnerHtml(usb_status_text, label_usb_loaded);
    usb_status.className = 'panel_good';
  } else {
    goog.dom.safe.setInnerHtml(usb_status_text, label_usb_unloaded);
    usb_status.className = 'panel_bad';
  }

  OnCheckButtonState();
}


/**
 * Updates Fixture load status.
 * @param {boolean} is_loaded Whether Fixture is loaded.
 */
function UpdateFixtureStatus(is_loaded) {
  g_is_fxt_loaded = is_loaded;

  var fxt_status = document.getElementById('fixture_status');
  var fxt_status_text = document.getElementById('fixture_status_text');

  if (is_loaded) {
    goog.dom.safe.setInnerHtml(fxt_status_text, label_fxt_loaded);
    fxt_status.className = 'panel_good';
  } else {
    goog.dom.safe.setInnerHtml(fxt_status_text, label_fxt_unloaded);
    fxt_status.className = 'panel_bad';
  }

  OnCheckButtonState();
}


/**
 * Updates StartTestButton status.
 * @param {boolean} is_sn_valid Whether Input SN is valid.
 */
function UpdateStartTestButtonStatus(is_sn_valid) {
  var button = GetStartTestButton();
  var sn_input_box = GetSnInputBox();
  if (!g_is_test_running &&
      (!g_use_usb || g_is_usb_loaded) &&
      (!g_use_fxt || g_is_fxt_loaded) &&
      (!g_use_sn_input || is_sn_valid)) {
    button.disabled = false;
  } else {
    button.disabled = true;
  }
}


////////////////////////////////////////////////////////////
// Event handlers
////////////////////////////////////////////////////////////


/**
 * When "Exit Test" button is clicked.
 */
function OnButtonExitTestClick() {
  window.test.sendTestEvent('exit_test_button_clicked', {});
}


/**
 * When "Start Test" button is clicked.
 */
function OnButtonStartTestClick() {
  if (!GetStartTestButton().disabled) {
    g_is_test_running = true;
    OnCheckButtonState();

    window.test.sendTestEvent(
        'start_test_button_clicked', {'input_sn': GetSnInputBox().value});
  }
}


/**
 * Clears "Serial Number" input box when it is clicked.
 */
function OnSnInputBoxClick() {
  if (g_use_sn_input) {
    var sn_input_box = GetSnInputBox();
    sn_input_box.value = '';
    sn_input_box.focus();
    OnCheckButtonState();
  }
}


/**
 * When the test is completed (no matter Passed or Failed).
 */
function OnTestCompleted() {
  g_is_test_running = false;
  OnSnInputBoxClick();
  OnCheckButtonState();
}


/**
 * Enables/disables 'Start Test' button according to the current status.
 *
 * This function should be called whenever the internal status is changed.
 *
 * Also send an event back to ui thread to handle the validity of serial number
 * when user types something. If everything ready, the event handler will
 * call back to js layer to make StartTestButton pressable.
 */
function OnCheckButtonState() {
  var sn_input_box = GetSnInputBox();

  window.test.sendTestEvent('sn_input_box_on_input',
                            {'input_sn': sn_input_box.value});
}


////////////////////////////////////////////////////////////
// Internal methods
////////////////////////////////////////////////////////////


function GetSnInputBox() {
  return document.getElementById('sn_input_box');
}


function GetStartTestButton() {
  return document.getElementById('button_start_test');
}
