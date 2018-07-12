// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import TextField from 'material-ui/TextField';
import React from 'react';
import {WrappedFieldProps} from 'redux-form';

interface RenderTextFieldArgs extends WrappedFieldProps {
  label: string;
  type?: string;
  hintText?: string;
}

export const renderTextField = ({
  input,
  label,
  meta: {error, touched},
  type = 'text',
  hintText = '',
}: RenderTextFieldArgs) => (
    <TextField
      fullWidth={true}
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
