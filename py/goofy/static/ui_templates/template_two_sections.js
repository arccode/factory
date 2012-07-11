// Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

function DrawProgressBar() {
  var container = document.getElementById('progress-bar-container');
  var element = document.getElementById('progress-bar');
  var progressBar = new parent.goog.ui.ProgressBar();

  container.style.display = 'inline';
  progressBar.decorate(element);
  progressBar.setValue(0.0);
  container.progressBar = progressBar;
}

function SetProgressBarValue(value) {
  var container = document.getElementById('progress-bar-container');
  var indicator = document.getElementById(
      'template-progress-bar-indicator');

  container.progressBar.setValue(value);
  indicator.innerHTML = value + '%';
}
