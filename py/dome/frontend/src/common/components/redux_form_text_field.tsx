// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import TextField from '@material-ui/core/TextField';
import React from 'react';
import {BaseFieldProps, Field, WrappedFieldProps} from 'redux-form';

interface RenderTextFieldProps {
  label: string;
  type?: string;
  placeholder?: string;
}

const renderTextField = ({
  input,
  meta: {error, touched},
  label,
  type = 'text',
  placeholder = '',
}: RenderTextFieldProps & WrappedFieldProps) => (
  <TextField
    fullWidth
    label={label}
    type={type}
    placeholder={placeholder}
    error={touched && error}
    helperText={touched && error}
    margin="normal"
    {...input}
  />
);

type ReduxFormTextFieldProps =
  RenderTextFieldProps & BaseFieldProps<RenderTextFieldProps>;

const ReduxFormTextField: React.SFC<ReduxFormTextFieldProps> =
  (props) => (
    <Field<RenderTextFieldProps> {...props} component={renderTextField} />
  );

export default ReduxFormTextField;
