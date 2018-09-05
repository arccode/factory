// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {
  InjectedFormProps,
  reduxForm,
} from 'redux-form';

import ReduxFormTextField from '@common/components/redux_form_text_field';
import {validateRequired} from '@common/form';

import {UPDATE_RESOURCE_FORM} from '../constants';

export interface UpdateResourceFormData {
  name: string;
  note: string;
}

interface UpdateResourceFormProps {
  bundleNames: string[];
}

class UpdateResourceForm extends React.Component<
  UpdateResourceFormProps
  & InjectedFormProps<UpdateResourceFormData, UpdateResourceFormProps>> {

  validateUnique = (value: string) => {
    return this.props.bundleNames.includes(value) ?
      `${value} already exist` : undefined;
  }

  render() {
    const {handleSubmit} = this.props;
    return (
      <form onSubmit={handleSubmit}>
        <ReduxFormTextField
          name="name"
          label="New Bundle Name"
          validate={[
            validateRequired,
            this.validateUnique,
          ]}
        />
        <ReduxFormTextField name="note" label="Note" />
      </form>
    );
  }
}

export default reduxForm<UpdateResourceFormData, UpdateResourceFormProps>({
  form: UPDATE_RESOURCE_FORM,
})(UpdateResourceForm);
