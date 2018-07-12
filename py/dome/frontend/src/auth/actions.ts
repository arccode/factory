// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import axios from 'axios';
import {Dispatch} from 'redux';
import {createAction} from 'typesafe-actions';

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

const loginFailed = createAction('LOGIN_FAILED', (resolve) =>
  () => {
    localStorage.removeItem('token');
    return resolve();
  });

export const logout = createAction('LOGOUT', (resolve) =>
  () => {
    localStorage.removeItem('token');
    return resolve();
  });

export const basicActions = {loginSucceed, loginFailed, logout};

export const tryLogin = (data: AuthData) => async (dispatch: Dispatch) => {
  try {
    const response = await axios.post('/auth', data);
    dispatch(loginSucceed(response.data.token));
  } catch (err) {
    dispatch(loginFailed());
    // TODO(pihsun): Don't use blocking window.alert.
    window.alert('\nLogin failed :(');
  }
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
  // Dispatch a login failed event to clear all wrong token.
  dispatch(loginFailed());
};
