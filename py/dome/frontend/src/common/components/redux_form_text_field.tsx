// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {PropTypes} from '@material-ui/core';
import TextField from '@material-ui/core/TextField';
import React from 'react';
import {BaseFieldProps, Field, WrappedFieldProps} from 'redux-form';

interface RenderTextFieldProps {
  label: string;
  type?: string;
  placeholder?: string;
  margin?: PropTypes.Margin;
}

const renderTextField = ({
  input,
  meta: {error, touched},
  ...props
}: RenderTextFieldProps & WrappedFieldProps) => (
  <TextField
    fullWidth
    error={!!(touched && error)}
    helperText={touched && error}
    margin="normal"
    {...input}
    {...props}
  />
);

type ReduxFormTextFieldProps =
  RenderTextFieldProps & BaseFieldProps<RenderTextFieldProps>;

const ReduxFormTextField: React.SFC<ReduxFormTextFieldProps> =
  (props) => (
    <Field<RenderTextFieldProps> {...props} component={renderTextField} />
  );

export default ReduxFormTextField;
