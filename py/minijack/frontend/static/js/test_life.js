// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  $('#buttons_div button').button();
  $('#buttons_div button').on('click', function() {
    var params = aParams;
    params['order'] = $(this).val();
    window.location.href = '?' + $.param(params);
  });
});
