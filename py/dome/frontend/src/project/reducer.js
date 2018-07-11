// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {combineReducers} from 'redux';

import actionTypes from './actionTypes';

const projectsReducer = produce((draft, action) => {
  switch (action.type) {
    case actionTypes.ADD_PROJECT:
      draft[action.project.name] = action.project;
      return;

    case actionTypes.DELETE_PROJECT:
      delete draft[action.projectName];
      return;

    case actionTypes.RECEIVE_PROJECTS:
      return action.projects.reduce((projectMap, project) => {
        projectMap[project.name] = {
          umpireReady: project.umpireEnabled,
          ...project,
        };
        return projectMap;
      }, {});

    case actionTypes.UPDATE_PROJECT:
      Object.assign(draft[action.project.name], action.project);
      return;
  }
}, {});

export default combineReducers({
  projects: projectsReducer,
  currentProject: (state = '', action) => {
    switch (action.type) {
      case actionTypes.SWITCH_PROJECT:
        return action.nextProject;

      default:
        return state;
    }
  },
});
