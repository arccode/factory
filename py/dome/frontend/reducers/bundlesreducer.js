// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import {arrayMove} from 'react-sortable-hoc';

import ActionTypes from '../constants/ActionTypes';
import UploadingTaskStates from '../constants/UploadingTaskStates';

const INITIAL_STATE = Immutable.fromJS({
  entries: [],
  isFetchingEntries: false,
  formVisibility: {
  },
  formPayload: {
  },
  uploadingTasks: {}
});

export default function bundlesReducer(state = INITIAL_STATE, action) {
  switch (action.type) {
    case ActionTypes.REQUEST_BUNDLES:
      return state.set('isFetchingEntries', true);

    case ActionTypes.RECEIVE_BUNDLES:
      return state.withMutations((s) => {
        s.set('isFetchingEntries', false);
        s.set('entries', Immutable.fromJS(action.bundles));
      });

    case ActionTypes.OPEN_FORM:
      return state.withMutations((s) => {
        s.setIn(['formVisibility', action.formName], true);
        s.mergeIn(['formPayload', action.formName], action.payload);
      });

    case ActionTypes.CLOSE_FORM:
      return state.setIn(['formVisibility', action.formName], false);

    case ActionTypes.CREATE_UPLOADING_TASK:
      return state.mergeIn(['uploadingTasks'], {
        [action.taskID]: {
          state: UploadingTaskStates.UPLOADING_TASK_STARTED,
          description: action.description
        }
      });

    case ActionTypes.CHANGE_UPLOADING_TASK_STATE:
      return state.setIn(
          ['uploadingTasks', action.taskID, 'state'], action.state);

    case ActionTypes.REMOVE_UPLOADING_TASK:
      return state.deleteIn(['uploadingTasks', action.taskID]);

    default:
      return state;
  }
};
