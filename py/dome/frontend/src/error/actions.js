// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import actionTypes from './actionTypes';

const setError = (message) => ({
  type: actionTypes.SET_ERROR_MESSAGE,
  message,
});

const showErrorDialog = () => ({
  type: actionTypes.SHOW_ERROR_DIALOG,
});

export const hideErrorDialog = () => ({
  type: actionTypes.HIDE_ERROR_DIALOG,
});

// convenient wrapper of setError() + showErrorDialog()
export const setAndShowErrorDialog = (message) => (dispatch) => {
  dispatch(setError(message));
  dispatch(showErrorDialog());
};
