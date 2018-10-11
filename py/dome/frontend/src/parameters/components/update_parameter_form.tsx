// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {
  InjectedFormProps,
  reduxForm,
} from 'redux-form';

import {UPDATE_PARAMETER_FORM} from '../constants';

class UpdateParameterForm extends React.Component<
  InjectedFormProps> {

  render() {
    return (
      <>
      </>
    );
  }
}

export default reduxForm<{}, {}>({
  form: UPDATE_PARAMETER_FORM,
})(UpdateParameterForm);
