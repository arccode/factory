// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';

import actionTypes from './actionTypes';

const INITIAL_STATE = Immutable.fromJS({
  projects: {},
  currentProject: '',
});

export default (state = INITIAL_STATE, action) => {
  switch (action.type) {
    case actionTypes.ADD_PROJECT:
      return state.setIn(['projects', action.project.name],
          Immutable.fromJS(action.project));

    case actionTypes.DELETE_PROJECT:
      return state.deleteIn(['projects', action.projectName]);

    case actionTypes.RECEIVE_PROJECTS:
      return state.set('projects', Immutable.Map(action.projects.map(
          (b) => [b['name'], Immutable.fromJS(b).merge({
            umpireReady: b['umpireEnabled'],
          })]
      )));

    case actionTypes.UPDATE_PROJECT:
      return state.mergeIn(['projects', action.project.name],
          Immutable.fromJS(action.project));

    case actionTypes.SWITCH_PROJECT:
      return state.withMutations((s) => {
        s.set('currentProject', action.nextProject);
      });

    default:
      return state;
  }
};
