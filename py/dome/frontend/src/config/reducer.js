// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import actionTypes from './actionTypes';

const INITIAL_STATE = Immutable.fromJS({
  updating: false,
  TFTPEnabled: false,
});

export default (state = INITIAL_STATE, action) => {
  switch (action.type) {
    case actionTypes.RECEIVE_CONFIG:
      return state.set('TFTPEnabled', action.config.tftpEnabled);

    case actionTypes.START_UPDATING_CONFIG:
      return state.set('updating', true);

    case actionTypes.FINISH_UPDATING_CONFIG:
      return state.set('updating', false);

    default:
      return state;
  }
};
