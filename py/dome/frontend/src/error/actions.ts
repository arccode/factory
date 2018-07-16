// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import {Dispatch} from '@app/types';

const setError = createAction('SET_ERROR_MESSAGE', (resolve) =>
  (message: string) => resolve({message}));

const showErrorDialog = createAction('SHOW_ERROR_DIALOG');

export const hideErrorDialog = createAction('HIDE_ERROR_DIALOG');

export const basicActions = {
  setError,
  showErrorDialog,
  hideErrorDialog,
};

// convenient wrapper of setError() + showErrorDialog()
export const setAndShowErrorDialog = (message: string) =>
  (dispatch: Dispatch) => {
    dispatch(setError(message));
    dispatch(showErrorDialog());
  };
