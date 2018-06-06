// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import actionTypes from './actionTypes';
import {AppNames} from './constants';

const INITIAL_STATE = Immutable.fromJS({
  // default app is the project selection page.
  currentApp: AppNames.PROJECTS_APP,
});

export default (state = INITIAL_STATE, action) => {
  switch (action.type) {
    case actionTypes.SWITCH_APP:
      return state.set('currentApp', action.nextApp);

    default:
      return state;
  }
};
