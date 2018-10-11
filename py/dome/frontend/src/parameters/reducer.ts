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
  loading: boolean;
}

type ParameterAction = ActionType<typeof actions>;

const INITIAL_STATE = {
  files: [],
  dirs: [],
  loading: false,
};

export default produce<ParameterState, ParameterAction>((draft, action) => {
  switch (action.type) {
    case getType(actions.receiveParameters): {
      const {parameters} = action.payload;
      draft.loading = false;
      draft.files = parameters;
      return;
    }

    case getType(actions.updateParameter): {
      const {parameter} = action.payload;
      draft.loading = false;
      draft.files[parameter.id] = parameter;
      return;
    }

    case getType(actions.receiveParameterDirs): {
      const {parameterDirs} = action.payload;
      draft.loading = false;
      draft.dirs = parameterDirs;
      return;
    }

    case getType(actions.updateParameterDir): {
      const {parameterDir} = action.payload;
      draft.loading = false;
      draft.dirs[parameterDir.id] = parameterDir;
      return;
    }

    case getType(actions.setLoading): {
      draft.loading = true;
      return;
    }

    default:
      return;
  }
}, INITIAL_STATE);
