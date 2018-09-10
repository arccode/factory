// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import axios from 'axios';
import {createAction} from 'typesafe-actions';

import {Dispatch} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {AuthData} from './types';

const loginSucceed = createAction('LOGIN_SUCCEED', (resolve) =>
  (token: string | null) => {
    if (token != null) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
    return resolve();
  });

export const logout = createAction('LOGOUT', (resolve) =>
  () => {
    localStorage.removeItem('token');
    return resolve();
  });

export const basicActions = {loginSucceed, logout};

export const tryLogin = (data: AuthData) => async (dispatch: Dispatch) => {
  const response = await axios.post('/auth', data);
  dispatch(loginSucceed(response.data.token));
};

export const testAuthToken = () => async (dispatch: Dispatch) => {
  const token = localStorage.getItem('token');
  if (token != null) {
    try {
      await authorizedAxios().get('/projects.json');
      dispatch(loginSucceed(token));
      return;
    } catch (err) {
      /* Authorization failed. */
    }
  }
  // We might not need a auth token, for example, login is not needed for
  // localhost.
  try {
    await axios.get('/projects.json');
    dispatch(loginSucceed(null));
    return;
  } catch (err) {
    /* Authorization failed. */
  }
  // Dispatch a logout event to clear all wrong token.
  dispatch(logout());
};
