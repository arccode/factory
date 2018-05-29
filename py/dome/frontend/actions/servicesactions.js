// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ActionTypes from '../constants/ActionTypes';

import DomeActions from './domeactions';
import TaskActions from './taskactions';

function baseURL(getState) {
  return `/projects/${getState().getIn(['dome', 'currentProject'])}`;
}

const updateService = (name, config) => async (dispatch, getState) => {
  const data = {[name]: config};

  const description = `update "${name}" service`;
  const {cancel} = await dispatch(TaskActions.runTask(
      description, 'PUT', `${baseURL(getState)}/services/`, data));
  if (!cancel) {
    dispatch({type: ActionTypes.UPDATE_SERVICE, name, config});
  }
};

const fetchServiceSchemata = () => async (dispatch, getState) => {
  const response = await DomeActions.authorizedFetch(
      baseURL(getState) + '/services/schema.json', {});
  const json = await response.json();
  dispatch(receiveServiceSchemata(json));
};

const fetchServices = () => async (dispatch, getState) => {
  const response = await DomeActions.authorizedFetch(
      baseURL(getState) + '/services.json', {});
  const json = await response.json();
  dispatch(receiveServices(json));
};

const receiveServiceSchemata = (schemata) => ({
  type: ActionTypes.RECEIVE_SERVICE_SCHEMATA,
  schemata,
});

const receiveServices = (services) => ({
  type: ActionTypes.RECEIVE_SERVICES,
  services,
});

export default {
  fetchServiceSchemata, fetchServices,
  receiveServiceSchemata, receiveServices, updateService,
};
