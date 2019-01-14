// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {Parameter, ParameterDirectory} from './types';

export interface ParameterState {
  files: Parameter[];
  dirs: ParameterDirectory[];
}

type ParameterAction = ActionType<typeof actions>;

const INITIAL_STATE = {
  files: [],
  dirs: [],
};

export default produce<ParameterState, ParameterAction>((draft, action) => {
  switch (action.type) {
    case getType(actions.receiveParameters): {
      const {parameters} = action.payload;
      draft.files = parameters;
      return;
    }

    case getType(actions.updateParameter): {
      const {parameter} = action.payload;
      draft.files[parameter.id] = parameter;
      return;
    }

    case getType(actions.receiveParameterDirs): {
      const {parameterDirs} = action.payload;
      draft.dirs = parameterDirs;
      return;
    }

    case getType(actions.updateParameterDir): {
      const {parameterDir} = action.payload;
      draft.dirs[parameterDir.id] = parameterDir;
      return;
    }

    default:
      return;
  }
}, INITIAL_STATE);
