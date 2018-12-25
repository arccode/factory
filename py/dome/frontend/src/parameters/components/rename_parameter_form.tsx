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

import {startRenameParameter} from '../actions';
import {RENAME_PARAMETER_FORM} from '../constants';
import {RenameRequest} from '../types';

const InnerFormComponent: React.SFC<InjectedFormProps<RenameRequest>> =
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

const InnerForm = reduxForm<RenameRequest>({
  form: RENAME_PARAMETER_FORM,
})(InnerFormComponent);

type RenameParameterFormProps =
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

class RenameParameterForm extends React.Component<RenameParameterFormProps> {
  render() {
    const {open, cancelRename, renameParameter, submitForm} = this.props;
    const initialValues = {
      id: this.props.payload.id,
      name: this.props.payload.name,
    };
    return (
      <Dialog open={open} onClose={cancelRename}>
        <DialogTitle>Rename Parameter</DialogTitle>
        <DialogContent>
          <InnerForm
            onSubmit={renameParameter}
            initialValues={initialValues}
          />
        </DialogContent>
        <DialogActions>
          <Button color="primary" onClick={submitForm}>Rename</Button>
          <Button onClick={cancelRename}>Cancel</Button>
        </DialogActions>
      </Dialog>
    );
  }
}

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(RENAME_PARAMETER_FORM);
const getFormPayload =
  formDialog.selectors.getFormPayloadFactory(RENAME_PARAMETER_FORM);

const mapStateToProps = (state: RootState) => ({
  open: isFormVisible(state),
  project: project.selectors.getCurrentProject(state),
  payload: getFormPayload(state)!,
});

const mapDispatchToProps = {
  submitForm: () => submit(RENAME_PARAMETER_FORM),
  cancelRename: () => formDialog.actions.closeForm(RENAME_PARAMETER_FORM),
  renameParameter: startRenameParameter,
};

export default connect(
  mapStateToProps, mapDispatchToProps)(RenameParameterForm);
