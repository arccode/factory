// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {AxiosError} from 'axios';
import React from 'react';
import {SubmissionError} from 'redux-form';

export const validateRequired = (value: any): string | undefined => (
  value ? undefined : 'Required'
);

export const parseNumber = (value: string) => {
  const num = Number(value);
  return value === '' || isNaN(num) ? null : num;
};

// When user press "enter" key in input elements of form, the default behavior
// is to trigger the first button in form that doesn't have type="button".
// Since we have many form which the submit button is NOT in the form, we need
// to add a hidden submit button in the form to make pressing "enter" work.
export const HiddenSubmitButton = () => (
  <button type="submit" style={{display: 'none'}} />
);

const DJANGO_FORM_ERROR_KEY = 'non_field_errors';

export const toReduxFormError = (err: AxiosError) => {
  const {response} = err;
  if (!response) {
    return err;
  }
  const {data} = response;
  if (typeof data !== 'object') {
    return err;
  }
  if (data.hasOwnProperty(DJANGO_FORM_ERROR_KEY)) {
    data._error = data[DJANGO_FORM_ERROR_KEY];
    delete data[DJANGO_FORM_ERROR_KEY];
  }
  return new SubmissionError(data);
};
