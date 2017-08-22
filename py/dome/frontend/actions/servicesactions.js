// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ActionTypes from '../constants/ActionTypes';
import DomeActions from './domeactions';

function baseURL(getState) {
  return `/projects/${getState().getIn(['dome', 'currentProject'])}`;
}

const updateService = (name, config) => (dispatch, getState) => {
  dispatch({
      type: ActionTypes.UPDATE_SERVICE,
      name,
      config
  });

  var data = {};
  data[name] = config;

  var description = `update "${name}" service`;
  dispatch(DomeActions.createTask(
      description, 'PUT',
      `${baseURL(getState)}/services`, data
  ));
};

const fetchServiceSchemata = () => (dispatch, getState) => {
  DomeActions.authorizedFetch(baseURL(getState) + '/services/schema.json', {})
  .then(response => {
    response.json().then(json => {
      dispatch(receiveServiceSchemata(json));
    }, error => {
      console.error('error parsing service schemata response');
      console.error(error);
    });
  }, error => {
    console.error('error fetching service schemata');
    console.error(error);
  });
};

const fetchServices = () => (dispatch, getState) => {
  DomeActions.authorizedFetch(baseURL(getState) + '/services.json', {})
  .then(response => {
    response.json().then(json => {
      dispatch(receiveServices(json));
    }, error => {
      console.error('error parsing services response');
      console.error(error);
    });
  }, error => {
    console.error('error fetching services');
    console.error(error);
  });
};

const receiveServiceSchemata = schemata => ({
  type: ActionTypes.RECEIVE_SERVICE_SCHEMATA,
  schemata
});

const receiveServices = services => ({
  type: ActionTypes.RECEIVE_SERVICES,
  services
});

export default {
  fetchServiceSchemata, fetchServices,
  receiveServiceSchemata, receiveServices, updateService
};
