// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var init = function(require_dongle, test_title) {
  if (!require_dongle) {
    document.getElementById('require_dongle').style.display = 'None';
  }
  document.getElementById('test_title').innerHTML = test_title;
};

var testInProgress = function(success_rate) {
  var msgs = document.getElementById('message');
  var _ = cros.factory.i18n.translation;
  msgs.innerHTML = '';
  if (success_rate != null) {
    msgs.appendChild(
        cros.factory.i18n.i18nLabelNode(cros.factory.i18n.stringFormat(
            _('Loopback testing...\nSuccess Rate: {success_rate}'),
              {'success_rate': success_rate})));
  } else {
    msgs.appendChild(
        cros.factory.i18n.i18nLabelNode('Loopback testing...'));
  }
};

var testFailResult = function(success_rate) {
  var msgs = document.getElementById('message');
  var _ = cros.factory.i18n.translation;
  msgs.innerHTML = '';
  msgs.appendChild(
      cros.factory.i18n.i18nLabelNode(cros.factory.i18n.stringFormat(
          _('Testing Result: Fail\nSuccess Rate: {success_rate}'),
            {'success_rate': success_rate})));
};

var testPassResult = function(success_rate) {
  var msgs = document.getElementById('message');
  msgs.innerHTML = '';
  msgs.appendChild(
      cros.factory.i18n.i18nLabelNode('Testing Result: Success!'));
};
