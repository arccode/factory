// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {connect} from 'react-redux';
import {
  InjectedFormProps,
  reduxForm,
  submit,
} from 'redux-form';

import formDialog from '@app/form_dialog';
import project from '@app/project';
import {RootState} from '@app/types';
import FileUploadDialog from '@common/components/file_upload_dialog';
import ReduxFormTextField from '@common/components/redux_form_text_field';
import {
  HiddenSubmitButton,
  validateRequired,
} from '@common/form';

import {startUploadBundle} from '../actions';
import {UPLOAD_BUNDLE_FORM} from '../constants';
import {UploadBundleRequestPayload} from '../types';

interface FormData {
  name: string;
  note: string;
}

const InnerFormComponent: React.SFC<InjectedFormProps<FormData>> =
  ({handleSubmit}) => (
    <form onSubmit={handleSubmit}>
      <ReduxFormTextField
        name="name"
        label="New Bundle Name"
        validate={validateRequired}
      />
      <ReduxFormTextField name="note" label="New Bundle Note" />
      <HiddenSubmitButton />
    </form>
  );

const InnerForm = reduxForm<FormData>({
  form: UPLOAD_BUNDLE_FORM,
  initialValues: {name: '', note: ''},
})(InnerFormComponent);

interface UploadBundleFormProps {
  open: boolean;
  submitForm: () => any;
  cancelUpload: () => any;
  startUpload: (data: UploadBundleRequestPayload) => any;
  project: string;
}

interface UploadBundleFormState {
  initialValues: Partial<FormData>;
}

class UploadBundleForm
  extends React.Component<UploadBundleFormProps, UploadBundleFormState> {
  state = {
    initialValues: {},
  };

  handleCancel = () => {
    this.props.cancelUpload();
  }

  handleSubmit = ({name, note, file}: FormData & {file: File}) => {
    const {project, startUpload} = this.props;

    const data = {
      project,
      name,
      note,
      bundleFile: file,
    };
    startUpload(data);
  }

  render() {
    const {open, submitForm} = this.props;
    return (
      <FileUploadDialog<FormData>
        title="Upload Bundle"
        open={open}
        onCancel={this.handleCancel}
        submitForm={submitForm}
        onSubmit={this.handleSubmit}
      >
        <InnerForm />
      </FileUploadDialog>
    );
  }
}

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(UPLOAD_BUNDLE_FORM);

const mapStateToProps = (state: RootState) => ({
  open: isFormVisible(state),
  project: project.selectors.getCurrentProject(state),
});

const mapDispatchToProps = {
  startUpload: startUploadBundle,
  cancelUpload: () => formDialog.actions.closeForm(UPLOAD_BUNDLE_FORM),
  submitForm: () => submit(UPLOAD_BUNDLE_FORM),
};

export default connect(
  mapStateToProps, mapDispatchToProps)(UploadBundleForm);
