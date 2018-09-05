// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {
  InjectedFormProps,
  reduxForm,
} from 'redux-form';

import ReduxFormTextField from '@common/components/redux_form_text_field';
import {
  HiddenSubmitButton,
  validateRequired,
} from '@common/form';

import {UPLOAD_BUNDLE_FORM} from '../constants';

export interface UploadBundleFormData {
  name: string;
  note: string;
}

interface UploadBundleFormProps {
  bundleNames: string[];
}

class UploadBundleForm extends React.Component<
  UploadBundleFormProps &
  InjectedFormProps<UploadBundleFormData, UploadBundleFormProps>> {

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
        <ReduxFormTextField name="note" label="New Bundle Note" />
        <HiddenSubmitButton />
      </form>
    );
  }
}

export default reduxForm<UploadBundleFormData, UploadBundleFormProps>({
  form: UPLOAD_BUNDLE_FORM,
  initialValues: {name: '', note: ''},
})(UploadBundleForm);
