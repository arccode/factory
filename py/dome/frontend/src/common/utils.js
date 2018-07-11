// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import axios from 'axios';

// add authentication token to header, if exists.
export const authorizedAxios = () => {
  const token = localStorage.getItem('token');
  const config = {};
  if (token != null) {
    config.headers = {
      'Authorization': `Token ${localStorage.getItem('token')}`,
    };
  }
  return axios.create(config);
};
