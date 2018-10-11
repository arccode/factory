// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import Dialog from '@material-ui/core/Dialog';
import DialogActions from '@material-ui/core/DialogActions';
import DialogContent from '@material-ui/core/DialogContent';
import DialogTitle from '@material-ui/core/DialogTitle';
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

import ReduxFormTextField from '@common/components/redux_form_text_field';
import {HiddenSubmitButton} from '@common/form';
import {DispatchProps} from '@common/types';

import {startCreateDirectory} from '../actions';
import {CREATE_DIRECTORY_FORM} from '../constants';
import {CreateDirectoryRequest} from '../types';

const InnerFormComponent: React.SFC<InjectedFormProps<CreateDirectoryRequest>> =
  ({handleSubmit}) => (
    <form onSubmit={handleSubmit}>
      <ReduxFormTextField
        name="name"
        label="name"
        type="string"
      />
      <HiddenSubmitButton />
    </form>
  );

const InnerForm = reduxForm<CreateDirectoryRequest>({
  form: CREATE_DIRECTORY_FORM,
})(InnerFormComponent);

interface CreateDirectoryFormOwnProps {
  dirId: number | null;
}

type CreateDirectoryFormProps =
  CreateDirectoryFormOwnProps &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

const CreateDirectoryForm: React.SFC<CreateDirectoryFormProps> = ({
  open,
  cancelCreate,
  createDirectory,
  submitForm,
  dirId,
}) => {
  const initialValues = {
    parentId: dirId,
  };
  return (
    <Dialog open={open} onClose={cancelCreate}>
      <DialogTitle>Create Directory</DialogTitle>
      <DialogContent>
        <InnerForm
          onSubmit={createDirectory}
          initialValues={initialValues}
        />
      </DialogContent>
      <DialogActions>
        <Button color="primary" onClick={submitForm}>Create</Button>
        <Button onClick={cancelCreate}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
};

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(CREATE_DIRECTORY_FORM);

const mapStateToProps = (state: RootState) => ({
  open: isFormVisible(state),
  project: project.selectors.getCurrentProject(state),
});

const mapDispatchToProps = {
  submitForm: () => submit(CREATE_DIRECTORY_FORM),
  cancelCreate: () => formDialog.actions.closeForm(CREATE_DIRECTORY_FORM),
  createDirectory: startCreateDirectory,
};

export default connect(
  mapStateToProps, mapDispatchToProps)(CreateDirectoryForm);
