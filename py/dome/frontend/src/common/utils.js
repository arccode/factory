// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import axios from 'axios';
import Immutable from 'immutable';

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

export const deepFilterKeys = (data, pred) => {
  const result = [];
  if (!Immutable.isAssociative(data)) {
    if (pred(data)) {
      result.push(Immutable.List());
    }
  } else {
    for (const [key, value] of data.toKeyedSeq()) {
      result.push(
          ...deepFilterKeys(value, pred).map((path) => path.unshift(key)));
    }
  }
  return result;
};
