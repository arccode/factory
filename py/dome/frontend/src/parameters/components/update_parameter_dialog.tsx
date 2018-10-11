// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {connect} from 'react-redux';
import {submit} from 'redux-form';

import formDialog from '@app/form_dialog';
import project from '@app/project';
import {RootState} from '@app/types';

import FileUploadDialog, {
  SelectProps,
} from '@common/components/file_upload_dialog';
import {DispatchProps} from '@common/types';

import {startUpdateParameter} from '../actions';
import {UPDATE_PARAMETER_FORM} from '../constants';

import UpdateParameterForm from './update_parameter_form';

type UpdateParameterDialogProps =
  ReturnType<typeof mapStateToProps> & DispatchProps<typeof mapDispatchToProps>;

class UpdateParameterDialog extends React.Component<
  UpdateParameterDialogProps> {

  handleCancel = () => {
    this.props.cancelUpdate();
  }

  handleSubmitOne = ({file}: {file: File}) => {
    const {
      project,
      startUpdate,
      payload,
    } = this.props;
    const data = {
      project,
      id: payload.id,
      dirId: payload.dirId,
    };
    if (payload.id == null) {
      startUpdate({...data, name: file.name, file});
    } else {
      startUpdate({...data, name: payload.name, file});
    }
  }

  handleSubmitMultiple = ({files}: {files: FileList}) => {
    const {
      project,
      startUpdate,
      payload,
    } = this.props;
    const data = {
      project,
      id: payload.id,
      dirId: payload.dirId,
    };
    for (const f of files) {
      startUpdate({...data, name: f.name, file: f});
    }
  }

  render() {
    const {open, submitForm, payload} = this.props;
    const {multiple} = payload;
    const selectProps: SelectProps =
      multiple ? {multiple, onSubmit: this.handleSubmitMultiple} :
        {multiple, onSubmit: this.handleSubmitOne};
    return (
      <FileUploadDialog
        open={open}
        title="Update Parameter"
        onCancel={this.handleCancel}
        submitForm={submitForm}
        {...selectProps}
      >
        <UpdateParameterForm />
      </FileUploadDialog>
    );
  }
}

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(UPDATE_PARAMETER_FORM);
const getFormPayload =
  formDialog.selectors.getFormPayloadFactory(UPDATE_PARAMETER_FORM);

const mapStateToProps = (state: RootState) => ({
  open: isFormVisible(state),
  project: project.selectors.getCurrentProject(state),
  payload: getFormPayload(state)!,
});

const mapDispatchToProps = {
  startUpdate: startUpdateParameter,
  cancelUpdate: () => formDialog.actions.closeForm(UPDATE_PARAMETER_FORM),
  submitForm: () => submit(UPDATE_PARAMETER_FORM),
};

export default connect(
  mapStateToProps, mapDispatchToProps)(UpdateParameterDialog);
