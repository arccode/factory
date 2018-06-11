// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {authorizedFetch} from '../common/utils';

import actionTypes from './actionTypes';

const loginSucceed = (token) => {
  if (token != null) {
    localStorage.setItem('token', token);
  } else {
    localStorage.removeItem('token');
  }
  return {type: actionTypes.LOGIN_SUCCEED};
};

const loginFailed = () => {
  localStorage.removeItem('token');
  return {type: actionTypes.LOGIN_FAILED};
};

export const tryLogin = (data) => async (dispatch) => {
  data = data.toJS();
  const response = await fetch('/auth', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const json = await response.json();
  const token = json['token'];
  if (token) {
    dispatch(loginSucceed(token));
  } else {
    dispatch(loginFailed());
    // TODO(pihsun): Don't use blocking window.alert.
    window.alert('\nLogin failed :(');
  }
};

export const testAuthToken = () => async (dispatch) => {
  const token = localStorage.getItem('token');
  if (token != null) {
    const resp = await authorizedFetch('/projects.json');
    if (resp.ok) {
      dispatch(loginSucceed(token));
      return;
    }
  }
  // We might not need a auth token, for example, login is not needed for
  // localhost.
  const resp = await fetch('/projects.json');
  if (resp.ok) {
    dispatch(loginSucceed(null));
  } else {
    dispatch(loginFailed());
  }
};

export const logout = () => (dispatch) => {
  localStorage.removeItem('token');
  dispatch({type: actionTypes.LOGOUT});
};
