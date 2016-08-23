// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// TODO(littlecvr): should be able to let user select board instead of typing
//                  the URL directly.
/**
 * Parse and return the board name from current URL.
 *
 * For example, if the URL is 'http://localhost:8080/totoro/' then the function
 * returns 'totoro'.
 */
function getCurrentBoard() {
  var board = null;
  var currentURL = location.pathname;
  var groups = new RegExp('/([^/]+)/').exec(currentURL);
  if (groups.length > 1) {
    board = groups[1];
  }
  return board;
}

export const BOARD = getCurrentBoard();
export const API_URL = '/boards/' + BOARD;
