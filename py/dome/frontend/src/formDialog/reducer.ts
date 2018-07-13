// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {FormNames, FormPayloadTypeMap} from './types';

export interface FormDialogState {
  visibility: {
    [K in FormNames]?: boolean;
  };
  payload: {
    [K in FormNames]?: FormPayloadTypeMap[K];
  };
}

type FormDialogAction = ActionType<typeof actions>;

const INITIAL_STATE = {
  visibility: {
  },
  payload: {
  },
};

export default produce<FormDialogState, FormDialogAction>(
  (draft: FormDialogState, action: FormDialogAction) => {
    switch (action.type) {
      case getType(actions.openFormImpl):
        const {payload} = action;
        draft.visibility[payload.formName] = true;
        draft.payload[payload.formName] = payload.formPayload;
        return;

      case getType(actions.closeForm):
        draft.visibility[action.payload.formName] = false;
        return;

      default:
        return;
    }
  }, INITIAL_STATE);
