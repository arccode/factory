// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {authorizedFetch} from '../common/utils';
import {runTask} from '../task/actions';

import actionTypes from './actionTypes';

function baseURL(getState) {
  return `/projects/${getState().getIn(['project', 'currentProject'])}`;
}

export const updateService = (name, config) => async (dispatch, getState) => {
  const data = {[name]: config};

  const description = `update "${name}" service`;
  const {cancel} = await dispatch(runTask(
      description, 'PUT', `${baseURL(getState)}/services/`, data));
  if (!cancel) {
    dispatch({type: actionTypes.UPDATE_SERVICE, name, config});
  }
};

export const fetchServiceSchemata = () => async (dispatch, getState) => {
  const response = await authorizedFetch(
      `${baseURL(getState)}/services/schema.json`);
  const json = await response.json();
  dispatch(receiveServiceSchemata(json));
};

export const fetchServices = () => async (dispatch, getState) => {
  const response = await authorizedFetch(`${baseURL(getState)}/services.json`);
  const json = await response.json();
  dispatch(receiveServices(json));
};

export const receiveServiceSchemata = (schemata) => ({
  type: actionTypes.RECEIVE_SERVICE_SCHEMATA,
  schemata,
});

export const receiveServices = (services) => ({
  type: actionTypes.RECEIVE_SERVICES,
  services,
});
