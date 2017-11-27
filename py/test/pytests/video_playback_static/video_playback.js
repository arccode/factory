// Copyright 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

window.init = (video_file, loop, time_limit, control_ui) => {
  var video_tag = document.getElementById('v');
  video_tag.src = video_file;
  video_tag.loop = loop;
  video_tag.controls = control_ui;
  setTimeout(() => window.test.pass(), time_limit * 1000);
  video_tag.play();
};
