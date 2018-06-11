// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {authorizedAxios} from '../common/utils';
import {runTask} from '../task/actions';

import actionTypes from './actionTypes';

export const receiveConfig = (config) => ({
  type: actionTypes.RECEIVE_CONFIG,
  config,
});

export const initializeConfig = () => (dispatch) => {
  const body = {};
  dispatch(fetchConfig(body));
};

export const fetchConfig = () => async (dispatch) => {
  const response = await authorizedAxios().get('/config/0');
  dispatch(receiveConfig(response.data));
};

export const updateConfig = (body) => async (dispatch, getState) => {
  dispatch({type: actionTypes.START_UPDATING_CONFIG});
  const description = 'Update config';
  const {cancel} = await dispatch(
      runTask(description, 'PUT', '/config/0/', body));
  if (!cancel) {
    await dispatch(fetchConfig());
    dispatch({type: actionTypes.FINISH_UPDATING_CONFIG});
  }
};

export const enableTFTP = () => (dispatch) => {
  const body = {
    tftp_enabled: true,
  };
  dispatch(updateConfig(body));
};

export const disableTFTP = () => (dispatch) => {
  const body = {
    tftp_enabled: false,
  };
  dispatch(updateConfig(body));
};
