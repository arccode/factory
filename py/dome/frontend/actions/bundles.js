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

const openForm = (formName, payload) => (dispatch, getState) => {
  // The file input does not fire any event when canceled, if the user opened
  // the file dialog and canceled, its onChange handler won't be called, the
  // form won't actually be opened, but its "show" attribute has already been
  // set to true.  Next time the user requests to open the form, the form won't
  // notice the difference and won't open. Therefore, we need to detect such
  // case -- close it first if it's already opened.
  const visible = getState().getIn(['bundles', 'formVisibility', formName]);
  const action = {
    type: ActionTypes.OPEN_FORM,
    formName,
    payload
  };
  if (!visible) {
    dispatch(action);
  }
  else {
    Promise.resolve()
        .then(() => dispatch(closeForm(formName)))
        .then(() => dispatch(action));
  }
};

const closeForm = formName => ({
  type: ActionTypes.CLOSE_FORM,
  formName
});

export default {
  fetchBundles,
  openForm,
  closeForm
};
