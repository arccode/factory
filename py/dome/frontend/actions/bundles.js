// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'babel-polyfill';
import fetch from 'isomorphic-fetch';

import {BOARD, API_URL} from '../common';
import ActionTypes from '../constants/ActionTypes';

const requestBundles = () => ({
  type: ActionTypes.REQUEST_BUNDLES
});

const receiveBundles = bundles => ({
  type: ActionTypes.RECEIVE_BUNDLES,
  bundles
});

const fetchBundles = () => dispatch => {
  // annouce that we're currenty fetching
  dispatch(requestBundles());

  fetch(`${API_URL}/bundles.json`).then(response => {
    response.json().then(json => {
      dispatch(receiveBundles(json));
    }, error => {
      // TODO(littlecvr): better error handling
      console.log('error parsing bundle list response');
      console.log(error);
    });
  }, error => {
    // TODO(littlecvr): better error handling
    console.log('error fetching bundle list');
    console.log(error);
  });
};

export default {
  fetchBundles
};
