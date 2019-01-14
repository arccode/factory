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

import {
  CREATE_DIRECTORY_FORM,
  RENAME_DIRECTORY_FORM,
  RENAME_PARAMETER_FORM,
  UPDATE_PARAMETER_FORM,
} from './constants';
import {getParameterDirs, getParameters} from './selector';
import {
  CreateDirectoryRequest,
  Parameter,
  ParameterDirectory,
  RenameRequest,
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

export const basicActions = {
  receiveParameters,
  updateParameter,
  receiveParameterDirs,
  updateParameterDir,
};

export const startCreateDirectory = (data: CreateDirectoryRequest) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    dispatch(formDialog.actions.closeForm(CREATE_DIRECTORY_FORM));

    const parameterDirs = getParameterDirs(getState());
    const optimisticUpdate = () => {
      let newParameterDir = parameterDirs.find((d) => (
        d.name === data.name && d.parentId === data.parentId));
      if (!newParameterDir) {
        newParameterDir = {
          id: parameterDirs.length,
          name: data.name,
          parentId: data.parentId,
        };
      }
      dispatch(updateParameterDir(newParameterDir));
    };

    // send the request
    const description = `Create Directory "${data.name}"`;
    const parameterDir =
      await dispatch(task.actions.runTask<ParameterDirectory>(
        description, 'POST', `${baseURL(getState)}/parameters/dirs/`, data,
        optimisticUpdate));
    dispatch(updateParameterDir(parameterDir));
  };

export const startUpdateParameter = (data: UpdateParameterRequest) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    dispatch(formDialog.actions.closeForm(UPDATE_PARAMETER_FORM));

    const parameters = getParameters(getState());
    const optimisticUpdate = () => {
      let newParameter = null;
      if (data.id == null) {
        newParameter = parameters.find((p) => (
          p.name === data.name && p.dirId === data.dirId));
        if (!newParameter) {
          newParameter = {
            id: parameters.length,
            dirId: data.dirId,
            name: data.name,
            usingVer: 0,
            revisions: [],
          };
        }
      } else {
        newParameter = parameters[data.id];
      }
      dispatch(updateParameter(newParameter));
    };

    // send the request
    const description = `Update parameter "${data.name}"`;
    const parameterComponent = await dispatch(task.actions.runTask<Parameter>(
      description, 'POST', `${baseURL(getState)}/parameters/files/`, data,
      optimisticUpdate));
    dispatch(updateParameter(parameterComponent));
  };

export const startUpdateComponentVersion =
  (data: UpdateParameterVersionRequest) =>
    async (dispatch: Dispatch, getState: () => RootState) => {
      // send the request
      const description = `Update parameter "${data.name}"  version`;
      const parameterComponent = await dispatch(task.actions.runTask<Parameter>(
        description, 'POST', `${baseURL(getState)}/parameters/files/`, data,
        () => {
          dispatch(updateParameter({
            ...getParameters(getState())[data.id], usingVer: data.usingVer}));
        }));
      dispatch(updateParameter(parameterComponent));
    };

export const startRenameParameter = (data: RenameRequest) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    dispatch(formDialog.actions.closeForm(RENAME_PARAMETER_FORM));
    // send the request
    const description = `Rename parameter "${data.name}"`;
    const parameterComponent = await dispatch(task.actions.runTask<Parameter>(
      description, 'POST', `${baseURL(getState)}/parameters/files/`, data,
      () => {
        dispatch(updateParameter({
          ...getParameters(getState())[data.id], name: data.name}));
      }));
    dispatch(updateParameter(parameterComponent));
  };

export const startRenameDirectory = (data: RenameRequest) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    dispatch(formDialog.actions.closeForm(RENAME_DIRECTORY_FORM));
    // send the request
    const description = `Rename directory "${data.name}"`;
    const directoryComponent =
      await dispatch(task.actions.runTask<ParameterDirectory>(
        description, 'POST', `${baseURL(getState)}/parameters/dirs/`, data,
        () => {
          dispatch(updateParameterDir({
            ...getParameterDirs(getState())[data.id], name: data.name}));
        }));
    dispatch(updateParameterDir(directoryComponent));
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
