// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import project from '@app/project';
import task from '@app/task';
import {Dispatch, RootState} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {SchemaMap, Service, ServiceMap} from './types';

const receiveServiceSchemata =
  createAction('RECEIVE_SERVICE_SCHEMATA', (resolve) =>
    (schemata: SchemaMap) => resolve({schemata}));

const receiveServices = createAction('RECEIVE_SERVICES', (resolve) =>
  (services: ServiceMap) => resolve({services}));

const updateServiceImpl = createAction('UPDATE_SERVICE', (resolve) =>
  (name: string, config: Service) => resolve({name, config}));

export const basicActions = {
  receiveServiceSchemata,
  receiveServices,
  updateServiceImpl,
};

const baseURL = (getState: () => RootState): string => {
  return `/projects/${project.selectors.getCurrentProject(getState())}`;
};

export const updateService = (name: string, config: Service) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    const data = {[name]: config};

    const description = `update "${name}" service`;
    await dispatch(task.actions.runTask(
      description, 'PUT', `${baseURL(getState)}/services/`, data));
    dispatch(updateServiceImpl(name, config));
  };

export const fetchServiceSchemata = () =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    const response = await authorizedAxios().get<SchemaMap>(
      `${baseURL(getState)}/services/schema.json`);
    dispatch(receiveServiceSchemata(response.data));
  };

export const fetchServices = () =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    const response = await authorizedAxios().get<ServiceMap>(
      `${baseURL(getState)}/services.json`);
    dispatch(receiveServices(response.data));
  };
