// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import ActionTypes from '../constants/ActionTypes';

const INITIAL_STATE = Immutable.fromJS({
  schemata: {},
  services: {},
});

export default function serviceReducer(state = INITIAL_STATE, action) {
  switch (action.type) {
    case ActionTypes.RECEIVE_SERVICE_SCHEMATA:
      return state.set('schemata',
          Immutable.fromJS(action.schemata));

    case ActionTypes.RECEIVE_SERVICES:
      return state.set('services',
          Immutable.fromJS(action.services));

    case ActionTypes.UPDATE_SERVICE:
      return state.setIn(['services', action.name],
          Immutable.fromJS(action.config));

    default:
      return state;
  }
}
