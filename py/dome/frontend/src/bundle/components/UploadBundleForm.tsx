// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import FlatButton from 'material-ui/FlatButton';
import React from 'react';
import {connect} from 'react-redux';
import {
  Field,
  InjectedFormProps,
  reduxForm,
  submit,
} from 'redux-form';

import formDialog from '@app/formDialog';
import project from '@app/project';
import {RootState} from '@app/types';
import FileUploadDialog from '@common/components/FileUploadDialog';
import {renderTextField, validateRequired} from '@common/form';

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
      <Field
        name="name"
        label="New Bundle Name"
        validate={validateRequired}
        component={renderTextField}
      />
      <Field name="note" label="New Bundle Note" component={renderTextField} />
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
        modal={false}
        onRequestClose={this.handleCancel}
        actions={[<>
          <FlatButton label="confirm" primary={true} onClick={submitForm} />
          <FlatButton label="cancel" onClick={this.handleCancel} />
        </>]}
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
