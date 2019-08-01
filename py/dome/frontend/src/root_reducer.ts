// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {combineReducers} from 'redux';
import {FormStateMap, reducer as reduxFormReducer} from 'redux-form';

import auth from '@app/auth';
import bundle from '@app/bundle';
import config from '@app/config';
import domeApp from '@app/dome_app';
import error from '@app/error';
import formDialog from '@app/form_dialog';
import log from '@app/log';
import parameter from '@app/parameters';
import project from '@app/project';
import service from '@app/service';
import task from '@app/task';

import {wrapReducer} from '@common/optimistic_update';

import {APP_STATE_ROOT} from './constants';

const appReducer = wrapReducer(combineReducers({
  [auth.constants.NAME]: auth.reducer,
  [bundle.constants.NAME]: bundle.reducer,
  [config.constants.NAME]: config.reducer,
  [domeApp.constants.NAME]: domeApp.reducer,
  [error.constants.NAME]: error.reducer,
  [formDialog.constants.NAME]: formDialog.reducer,
  [log.constants.NAME]: log.reducer,
  [parameter.constants.NAME]: parameter.reducer,
  [project.constants.NAME]: project.reducer,
  [service.constants.NAME]: service.reducer,
  [task.constants.NAME]: task.reducer,
}));

export type RootState = ReturnType<typeof appReducer> & {form: FormStateMap};

export default combineReducers({
  [APP_STATE_ROOT]: appReducer,
  // The redux-form reducer need to be mounted at root state, on key "form".
  form: reduxFormReducer,
});
