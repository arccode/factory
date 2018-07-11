// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';

import actionTypes from './actionTypes';

const INITIAL_STATE = {
  // default app is the project selection page.
  visibility: {
  },
  payload: {
  },
};

export default produce((draft, action) => {
  switch (action.type) {
    case actionTypes.OPEN_FORM:
      draft.visibility[action.formName] = true;
      draft.payload[action.formName] = action.payload;
      return;

    case actionTypes.CLOSE_FORM:
      draft.visibility[action.formName] = false;
      return;
  }
}, INITIAL_STATE);
