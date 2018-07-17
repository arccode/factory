// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {SchemaMap, ServiceMap} from './types';

export interface ServiceState {
  schemata: SchemaMap;
  services: ServiceMap;
}

type ServiceAction = ActionType<typeof actions>;

export default combineReducers<ServiceState, ServiceAction>({
  schemata: (state = {}, action: ServiceAction) => {
    switch (action.type) {
      case getType(actions.receiveServiceSchemata):
        return action.payload.schemata;

      default:
        return state;
    }
  },
  services: produce((draft: ServiceMap, action: ServiceAction) => {
    switch (action.type) {
      case getType(actions.receiveServices):
        return action.payload.services;

      case getType(actions.updateServiceImpl):
        draft[action.payload.name] = action.payload.config;
        return;

      default:
        return;
    }
  }, {}),
});
