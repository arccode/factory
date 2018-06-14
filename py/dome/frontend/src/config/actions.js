// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import task from '@app/task';
import {authorizedAxios} from '@common/utils';

import actionTypes from './actionTypes';

const receiveConfig = (config) => ({
  type: actionTypes.RECEIVE_CONFIG,
  config,
});

export const fetchConfig = () => async (dispatch) => {
  const response = await authorizedAxios().get('/config/0');
  dispatch(receiveConfig(response.data));
};

export const updateConfig = (body) => async (dispatch, getState) => {
  dispatch({type: actionTypes.START_UPDATING_CONFIG});
  const description = 'Update config';
  const {cancel} = await dispatch(
      task.actions.runTask(description, 'PUT', '/config/0/', body));
  if (!cancel) {
    await dispatch(fetchConfig());
    dispatch({type: actionTypes.FINISH_UPDATING_CONFIG});
  }
};

export const enableTFTP = () => updateConfig({tftp_enabled: true});

export const disableTFTP = () => updateConfig({tftp_enabled: false});
