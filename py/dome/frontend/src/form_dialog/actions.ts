// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import {Dispatch, RootState} from '@app/types';

import {isFormVisibleFactory} from './selectors';
import {FormDataType, FormNames, FormPayloadTypeMap} from './types';

const openFormImpl = createAction('OPEN_FORM', (resolve) =>
  (payload: FormDataType) => resolve(payload));

export const closeForm = createAction('CLOSE_FORM', (resolve) =>
  (formName: FormNames) => resolve({formName: formName as FormNames}));

export const basicActions = {openFormImpl, closeForm};

export const openForm = <T extends FormNames>(
  formName: T, formPayload: FormPayloadTypeMap[T] = {}) =>
  (dispatch: Dispatch, getState: () => RootState) => {
    // The file input does not fire any event when canceled, if the user
    // opened the file dialog and canceled, its onChange handler won't be
    // called, the form won't actually be opened, but its "show" attribute
    // has already been set to true.  Next time the user requests to open the
    // form, the form won't notice the difference and won't open. Therefore,
    // we need to detect such case -- close it first if it's already opened.
    const visible = isFormVisibleFactory(formName)(getState());
    const action = openFormImpl({formName, formPayload} as FormDataType);
    if (!visible) {
      dispatch(action);
    } else {
      dispatch(closeForm(formName));
      setTimeout(() => dispatch(action), 0);
    }
  };
