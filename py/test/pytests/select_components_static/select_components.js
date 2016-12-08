// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var componentFields = [];

function addComponentField(f) {
  componentFields.push(f);
}

function SelectComponents() {
  var length = componentFields.length;
  var eventData = [];
  for (var i = 0; i < length; ++i) {
    var componentSelector =
        document.getElementById('Select-' + componentFields[i]);
    var selectedIndex = componentSelector.selectedIndex;
    eventData.push([i, componentSelector.options[selectedIndex].value]);
  }
  window.test.sendTestEvent('Select-Components', eventData);
  window.test.pass();
}
