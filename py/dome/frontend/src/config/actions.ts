// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import task from '@app/task';
import {Dispatch, RootState} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {getConfig} from './selectors';
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

export const updateConfig = (config: Partial<Config>) =>
  (dispatch: Dispatch, getState: () => RootState) => {
    const newConfig = {...getConfig(getState()), ...config};
    dispatch(task.actions.runTask(
      'Update config', 'PUT', '/config/0/', newConfig, () => {
        // optimistic update
        dispatch(receiveConfig(newConfig));
      }))
  };

export const enableTftp = () => updateConfig({tftpEnabled: true});

export const disableTftp = () => updateConfig({tftpEnabled: false});

export const enableMcast = () => updateConfig({mcastEnabled: true});

export const disableMcast = () => updateConfig({mcastEnabled: false});
