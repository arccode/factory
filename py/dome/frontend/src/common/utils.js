// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// add authentication token to header, if exists.
export const authorizedFetch = (url, req = {}) => {
  const token = localStorage.getItem('token');
  if (token != null) {
    if (!req.hasOwnProperty('headers')) {
      req['headers'] = {};
    }
    req['headers']['Authorization'] = 'Token ' + localStorage.getItem('token');
  }
  return fetch(url, req);
};
