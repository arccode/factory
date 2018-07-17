// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {ProjectMap} from './types';

export interface ProjectState {
  projects: ProjectMap;
  currentProject: string;
}

type ProjectAction = ActionType<typeof actions>;

const projectsReducer = produce((draft: ProjectMap, action: ProjectAction) => {
  switch (action.type) {
    case getType(actions.deleteProjectImpl):
      delete draft[action.payload.project];
      return;

    case getType(actions.receiveProjects):
      return action.payload.projects.reduce((projectMap, project) => {
        projectMap[project.name] = {
          umpireReady: project.umpireEnabled,
          ...project,
        };
        return projectMap;
      }, {} as ProjectMap);

    case getType(actions.updateProjectImpl): {
      Object.assign(draft[action.payload.name], action.payload.project);
      return;
    }

    default:
      return;
  }
}, {});

export default combineReducers<ProjectState, ProjectAction>({
  projects: projectsReducer,
  currentProject: (state = '', action: ProjectAction) => {
    switch (action.type) {
      case getType(actions.switchProjectImpl):
        return action.payload.nextProject;

      default:
        return state;
    }
  },
});
