// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import actionTypes from './actionTypes';
import {isFormVisibleFactory} from './selectors';

export const openForm = (formName, payload) => (dispatch, getState) => {
  // The file input does not fire any event when canceled, if the user opened
  // the file dialog and canceled, its onChange handler won't be called, the
  // form won't actually be opened, but its "show" attribute has already been
  // set to true.  Next time the user requests to open the form, the form won't
  // notice the difference and won't open. Therefore, we need to detect such
  // case -- close it first if it's already opened.
  const visible = isFormVisibleFactory(formName)(getState());
  const action = {
    type: actionTypes.OPEN_FORM,
    formName,
    payload,
  };
  if (!visible) {
    dispatch(action);
  } else {
    dispatch(closeForm(formName));
    setTimeout(() => dispatch(action), 0);
  }
};

export const closeForm = (formName) => ({
  type: actionTypes.CLOSE_FORM,
  formName,
});
