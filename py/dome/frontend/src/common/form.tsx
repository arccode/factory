// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {default as V0TextField} from 'material-ui/TextField';
import React from 'react';
import {WrappedFieldProps} from 'redux-form';

interface RenderTextFieldProps {
  label: string;
  type?: string;
  hintText?: string;
}

// TODO(pihsun): Remove this and rename renderTextFieldV1 to renderTextField
// after all caller are migrated to use Material-UI v1.
export const renderTextField = ({
  input,
  label,
  meta: {error, touched},
  type = 'text',
  hintText = '',
}: RenderTextFieldProps & WrappedFieldProps) => (
  <V0TextField
    fullWidth
    floatingLabelText={label}
    type={type}
    hintText={hintText}
    errorText={touched && error}
    {...input}
  />
);

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
