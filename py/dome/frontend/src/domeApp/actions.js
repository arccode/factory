// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ActionTypes from './actionTypes';
import {getCurrentApp} from './selectors';

export const switchApp = (nextApp) => (dispatch, getState) => dispatch({
  type: ActionTypes.SWITCH_APP,
  prevApp: getCurrentApp(getState()),
  nextApp,
});
