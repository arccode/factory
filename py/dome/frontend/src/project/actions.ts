// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import domeApp from '@app/dome_app';
import task from '@app/task';
import {Dispatch, RootState} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {Project, UmpireServerResponse, UmpireSetting} from './types';

const updateProjectImpl = createAction('UPDATE_PROJECT', (resolve) =>
  (name: string, project: Partial<Project>) => resolve({name, project}));

const switchProjectImpl = createAction('SWITCH_PROJECT', (resolve) =>
  (nextProject: string) => resolve({nextProject}));

const receiveProjects = createAction('RECEIVE_PROJECTS', (resolve) =>
  (projects: Project[]) => resolve({projects}));

const deleteProjectImpl = createAction('DELETE_PROJECT', (resolve) =>
  (project: string) => resolve({project}));

export const basicActions = {
  updateProjectImpl,
  switchProjectImpl,
  receiveProjects,
  deleteProjectImpl,
};

export const createProject = (name: string) => async (dispatch: Dispatch) => {
  const description = `Create project "${name}"`;
  await dispatch(
    task.actions.runTask(description, 'POST', '/projects/', {name}));
  await dispatch(fetchProjects());
};

export const updateProject = (
  name: string,
  settings: Partial<UmpireSetting> = {},
  description?: string,
) => async (dispatch: Dispatch, getState: () => RootState) => {
  const body = {name, ...settings};

  const optimisticUpdate = () => {
    const update: Partial<Project> = {umpireReady: false, ...settings};
    if (settings.umpireEnabled != null) {
      update.hasExistingUmpire = settings.umpireEnabled;
    }
    dispatch(updateProjectImpl(name, update));
  };

  description = description || `Update project "${name}"`;
  const data = await dispatch(
    task.actions.runTask<UmpireServerResponse>(
      description, 'PUT', `/projects/${name}/`, body, optimisticUpdate));
  dispatch(updateProjectImpl(name, {
    umpireReady: data.umpireEnabled,
  }));
};

export const deleteProject = (name: string) =>
  (dispatch: Dispatch, getState: () => RootState) => (
    dispatch(task.actions.runTask(
      `Delete project "${name}"`, 'DELETE', `/projects/${name}/`, {}, () => {
        // optimistic update
        dispatch(deleteProjectImpl(name));
      }))
  );

export const fetchProjects = () => async (dispatch: Dispatch) => {
  const response = await authorizedAxios().get<Project[]>('/projects.json');
  dispatch(receiveProjects(response.data));
};

export const switchProject = (nextProject: string) =>
  (dispatch: Dispatch, getState: () => RootState) => {
    dispatch(switchProjectImpl(nextProject));
    // switch to dashboard after switching project by default
    dispatch(domeApp.actions.switchApp('DASHBOARD_APP'));
  };
