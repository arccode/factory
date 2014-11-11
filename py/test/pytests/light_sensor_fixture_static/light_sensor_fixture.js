// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Label constants
var label_usb_loaded = '<span class="goofy-label-en">LOADED</span>' +
    '<span class="goofy-label-zh">已载入</span>';
var label_usb_unloaded = '<span class="goofy-label-en">UNLOADED</span>' +
    '<span class="goofy-label-zh">未载入</span>';
var label_fxt_avail = '<span class="goofy-label-en">OK</span>' +
    '<span class="goofy-label-zh">已连接</span>';
var label_fxt_unavail = '<span class="goofy-label-en">UNAVAILABLE</span>' +
    '<span class="goofy-label-zh">未连接</span>';
var label_fxt_detecting = '<span class="goofy-label-en">DETECTING</span>' +
    '<span class="goofy-label-zh">侦测中</span>';
var label_state_idle = '<span class="color_idle goofy-label-en">IDLE</span>' +
    '<span class="color_idle goofy-label-zh">閒置中</span>';

// Whether to load/store data on USB drive.
var g_use_usb = true;

// Whether to load/store data to shopfloor.
var g_use_shopfloor = false;

// Whether to use Enter key to start test
var g_use_enter_key = false;

window.onkeydown = function(event) {
    if ((g_use_enter_key && event.keyCode == 13) || event.keyCode == 32) {
        var testButton = document.getElementById("btn_run_test");
        if (!testButton.disabled)
            ButtonRunTestClick();
    }
}

function InitLayout(talkToFixture, talkToShopfloor, ignoreEnterKey) {
    if (talkToShopfloor) {
        g_use_shopfloor = true;
        g_use_usb = false;
        document.getElementById("prompt_usb").hidden = true;
        document.getElementById("usb_status_panel").hidden = true;
        document.getElementById("prompt_ethernet").hidden = false;
    } else {
        g_use_shopfloor = false;
        g_use_usb = true;
        document.getElementById("prompt_usb").hidden = false;
        document.getElementById("usb_status_panel").hidden = false;
        document.getElementById("prompt_ethernet").hidden = true;
    }

    g_use_enter_key = !ignoreEnterKey;
}

function UpdateTestBottonStatus() {
    var testButton = document.getElementById("btn_run_test");
    var isUSBReady = (!g_use_usb ||
        document.getElementById('usb_status').innerHTML == label_usb_loaded);
    var isFixtureReady = (
        document.getElementById('fixture_status').innerHTML == label_fxt_avail);

    testButton.disabled = !(isUSBReady && isFixtureReady);
}

function OnShopfloorInit() {
    document.getElementById("prompt_ethernet").hidden = true;
    document.getElementById("container").hidden = false;
}

function OnUSBInsertion() {
    document.getElementById("usb_status").innerHTML = label_usb_loaded;
    document.getElementById("test_param").className = "panel_good";
    UpdateTestBottonStatus();
}

function OnUSBInit() {
    document.getElementById("prompt_usb").hidden = true;
    document.getElementById("container").hidden = false;
    document.getElementById("usb_status").innerHTML = label_usb_loaded;
    document.getElementById("test_param").className = "panel_good";
}

function OnUSBRemoval() {
    document.getElementById("usb_status").innerHTML = label_usb_unloaded;
    document.getElementById("test_param").className = "panel_bad";
    UpdateTestBottonStatus();
}

function OnAddFixtureConnection() {
    document.getElementById("fixture_status").innerHTML = label_fxt_avail;
    document.getElementById("test_fixture").className = "panel_good";
    UpdateTestBottonStatus();
}

function OnRemoveFixtureConnection() {
    document.getElementById("fixture_status").innerHTML = label_fxt_unavail;
    document.getElementById("test_fixture").className = "panel_bad";
    UpdateTestBottonStatus();
}

function OnDetectFixtureConnection() {
    document.getElementById("fixture_status").innerHTML = label_fxt_detecting;
    document.getElementById("test_fixture").className = "panel_bad";
    UpdateTestBottonStatus();
}

function ButtonRunTestClick() {
    var testButton = document.getElementById("btn_run_test");
    testButton.disabled = true;
    test.sendTestEvent("start_test_button_clicked", {});
    testButton.disabled = false;
    UpdateTestBottonStatus();
}

function ButtonExitTestClick() {
    test.sendTestEvent("exit_test_button_clicked", {});
}

function ResetUiData() {
    UpdateTestStatus(label_state_idle);
    UpdatePrograssBar("0%");
}

function UpdateTestStatus(msg) {
    var statusText = document.getElementById("test_status");
    statusText.innerHTML = msg;
}

function UpdatePrograssBar(progress) {
    var pBar = document.getElementById("progress_bar");
    pBar.style.width = progress;
}
