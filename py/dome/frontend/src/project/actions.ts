// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import domeApp from '@app/dome_app';
import task from '@app/task';
import {Dispatch, RootState} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {getProjects} from './selectors';
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

// TODO(pihsun): Have a better way to handle task cancellation.
const buildOnCancel = (dispatch: Dispatch, getState: () => RootState) => {
  const projectsSnapshot = getProjects(getState());
  return () => dispatch(receiveProjects(Object.values(projectsSnapshot)));
};

export const createProject = (name: string) => async (dispatch: Dispatch) => {
  const description = `Create project "${name}"`;
  const {cancel} = await dispatch(
    task.actions.runTask(description, 'POST', '/projects/', {name}));
  if (!cancel) {
    await dispatch(fetchProjects());
  }
};

export const updateProject =
  (name: string, settings: Partial<UmpireSetting> = {}) =>
    async (dispatch: Dispatch, getState: () => RootState) => {
      const body = {name, ...settings};

      // taking snapshot must be earlier than optimistic update
      const onCancel = buildOnCancel(dispatch, getState);

      // optimistic update
      dispatch(updateProjectImpl(
        name,
        {umpireReady: false, ...settings}));

      const description = `Update project "${name}"`;
      const result = await dispatch(
        task.actions.runTask<UmpireServerResponse>(
          description, 'PUT', `/projects/${name}/`, body));
      if (result.cancel) {
        onCancel();
        return;
      }
      const {response} = result;
      const data = response.data;
      // WORKAROUND: Umpire is not ready as soon as it should be,
      // wait for 1 second to prevent the request from failing.
      // TODO(b/65393817): remove the timeout after the issue has been solved.
      setTimeout(() => {
        dispatch(updateProjectImpl(name, {
          umpireVersion: data.umpireVersion,
          isUmpireRecent: data.isUmpireRecent,
          umpireReady: data.umpireEnabled,
        }));
      }, 1000);
    };

export const deleteProject = (name: string) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    const onCancel = buildOnCancel(dispatch, getState);

    // optimistic update
    dispatch(deleteProjectImpl(name));

    const {cancel} = await dispatch(task.actions.runTask(
      `Delete project "${name}"`, 'DELETE', `/projects/${name}/`, {}));

    if (cancel) {
      onCancel();
    }
  };

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
