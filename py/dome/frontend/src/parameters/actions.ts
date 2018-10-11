// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import error from '@app/error';
import formDialog from '@app/form_dialog';
import project from '@app/project';
import task from '@app/task';
import {Dispatch, RootState} from '@app/types';

import {authorizedAxios} from '@common/utils';

import {CREATE_DIRECTORY_FORM, UPDATE_PARAMETER_FORM} from './constants';
import {
  CreateDirectoryRequest,
  Parameter,
  ParameterDirectory,
  UpdateParameterRequest,
  UpdateParameterVersionRequest,
} from './types';

const baseURL = (getState: () => RootState): string => {
  return `/projects/${project.selectors.getCurrentProject(getState())}`;
};

const receiveParameters = createAction('RECEIVE_PARAMETERS', (resolve) =>
  (parameters: Parameter[]) => resolve({parameters}));

const receiveParameterDirs = createAction('RECEIVE_PARAMETER_DIRS', (resolve) =>
  (parameterDirs: ParameterDirectory[]) => resolve({parameterDirs}));

const updateParameter = createAction('UPDATE_PARAMETER', (resolve) =>
  (parameter: Parameter) => resolve({parameter}));

const updateParameterDir = createAction('UPDATE_PARAMETER_DIR', (resolve) =>
  (parameterDir: ParameterDirectory) => resolve({parameterDir}));

const setLoading = createAction('LOADING');

export const basicActions = {
  receiveParameters,
  updateParameter,
  receiveParameterDirs,
  updateParameterDir,
  setLoading,
};

export const startCreateDirectory = (data: CreateDirectoryRequest) =>
    async (dispatch: Dispatch, getState: () => RootState) => {
  dispatch(formDialog.actions.closeForm(CREATE_DIRECTORY_FORM));
  // send the request
  const description = `Create Directory "${data.name}"`;
  const parameterDir = await dispatch(task.actions.runTask<ParameterDirectory>(
      description, 'POST', `${baseURL(getState)}/parameters/dirs/`, data));
  dispatch(updateParameterDir(parameterDir));
};

export const startUpdateParameter =
    (data: UpdateParameterRequest) =>
    async (dispatch: Dispatch, getState: () => RootState) => {
  dispatch(formDialog.actions.closeForm(UPDATE_PARAMETER_FORM));

  // send the request
  const description = `Update parameter "${data.name}"`;
  dispatch(setLoading());
  const parameterComponent = await dispatch(task.actions.runTask<Parameter>(
      description, 'POST', `${baseURL(getState)}/parameters/files/`, data));
  dispatch(updateParameter(parameterComponent));
};

export const startUpdateComponentVersion =
    (data: UpdateParameterVersionRequest) =>
        async (dispatch: Dispatch, getState: () => RootState) => {
      // send the request
      const description = `Update parameter "${data.name}"  version`;
      const parameterComponent = await dispatch(task.actions.runTask<Parameter>(
          description, 'POST', `${baseURL(getState)}/parameters/files/`, data));
      dispatch(updateParameter(parameterComponent));
    };

export const fetchParameters = () =>
    async (dispatch: Dispatch, getState: () => RootState) => {
  try {
    const components = await authorizedAxios().get<Parameter[]>(
        `${baseURL(getState)}/parameters/files.json`);
    dispatch(receiveParameters(components.data));
    const directories = await authorizedAxios().get<ParameterDirectory[]>(
        `${baseURL(getState)}/parameters/dirs.json`);
    dispatch(receiveParameterDirs(directories.data));
  } catch (err) {
    dispatch(error.actions.setAndShowErrorDialog(
        `error fetching parameters or dirs\n\n${err.message}`));
  }
};
