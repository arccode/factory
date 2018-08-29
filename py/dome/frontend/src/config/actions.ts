// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import task from '@app/task';
import {Dispatch} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {Config} from './types';

const receiveConfig = createAction('RECEIVE_CONFIG', (resolve) =>
  (config: Config) => resolve({config}));

const startUpdatingConfig = createAction('START_UPDATING_CONFIG');

const finishUpdatingConfig = createAction('FINISH_UPDATING_CONFIG');

export const basicActions = {
  receiveConfig,
  startUpdatingConfig,
  finishUpdatingConfig,
};

export const fetchConfig = () => async (dispatch: Dispatch) => {
  const response = await authorizedAxios().get<Config>('/config/0');
  dispatch(receiveConfig(response.data));
};

export const updateConfig = (config: Config) =>
  (dispatch: Dispatch) => (
    dispatch(task.actions.runTask(
      'Update config', 'PUT', '/config/0/', config, () => {
        // optimistic update
        dispatch(receiveConfig(config));
      }))
  );

export const enableTftp = () => updateConfig({tftpEnabled: true});

export const disableTftp = () => updateConfig({tftpEnabled: false});
