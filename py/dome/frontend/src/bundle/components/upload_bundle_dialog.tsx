// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {connect} from 'react-redux';
import {
  submit,
} from 'redux-form';

import formDialog from '@app/form_dialog';
import project from '@app/project';
import {RootState} from '@app/types';

import FileUploadDialog from '@common/components/file_upload_dialog';
import {DispatchProps} from '@common/types';

import {startUploadBundle} from '../actions';
import {UPLOAD_BUNDLE_FORM} from '../constants';
import {getBundleNames} from '../selectors';

import UploadBundleForm, {UploadBundleFormData} from './upload_bundle_form';

type UploadBundleDialogProps =
  ReturnType<typeof mapStateToProps> & DispatchProps<typeof mapDispatchToProps>;

interface UploadBundleDialogState {
  initialValues: Partial<UploadBundleFormData>;
}

class UploadBundleDialog
  extends React.Component<UploadBundleDialogProps, UploadBundleDialogState> {
  state = {
    initialValues: {},
  };

  handleCancel = () => {
    this.props.cancelUpload();
  }

  handleSubmit = ({name, note, file}: UploadBundleFormData & {file: File}) => {
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
    const {open, submitForm, bundleNames} = this.props;
    return (
      <FileUploadDialog<UploadBundleFormData>
        title="Upload Bundle"
        open={open}
        onCancel={this.handleCancel}
        submitForm={submitForm}
        onSubmit={this.handleSubmit}
      >
        <UploadBundleForm bundleNames={bundleNames} />
      </FileUploadDialog>
    );
  }
}

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(UPLOAD_BUNDLE_FORM);

const mapStateToProps = (state: RootState) => ({
  open: isFormVisible(state),
  project: project.selectors.getCurrentProject(state),
  bundleNames: getBundleNames(state),
});

const mapDispatchToProps = {
  startUpload: startUploadBundle,
  cancelUpload: () => formDialog.actions.closeForm(UPLOAD_BUNDLE_FORM),
  submitForm: () => submit(UPLOAD_BUNDLE_FORM),
};

export default connect(
  mapStateToProps, mapDispatchToProps)(UploadBundleDialog);
