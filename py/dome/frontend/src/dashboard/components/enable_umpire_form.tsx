// Copyright 2016 The Chromium OS Authors. All rights reserved.
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
import {Project} from '@app/project/types';
import {RootState} from '@app/types';

import ReduxFormTextField from '@common/components/redux_form_text_field';
import {HiddenSubmitButton, parseNumber} from '@common/form';
import {DispatchProps} from '@common/types';

import {ENABLE_UMPIRE_FORM} from '../constants';

interface FormProps {
  hasExisting: boolean;
  projectName: string;
}

interface FormData {
  umpirePort?: number;
}

const InnerFormComponent: React.SFC<
  FormProps & InjectedFormProps<FormData, FormProps>> =
  ({hasExisting, projectName, handleSubmit}) => (
    <form onSubmit={handleSubmit}>
      {hasExisting ? (
        `Umpire container for ${projectName} already exists,` +
        ' it would be added to Dome.'
      ) : (
        <ReduxFormTextField
          name="umpirePort"
          label="port"
          type="number"
          parse={parseNumber}
        />
      )}
      <HiddenSubmitButton />
    </form>
  );

const InnerForm = reduxForm<FormData, FormProps>({
  form: ENABLE_UMPIRE_FORM,
})(InnerFormComponent);

interface EnableUmpireFormOwnProps {
  project: Project;
  onCancel: () => any;
  onSubmit: (values: FormData) => any;
}

type EnableUmpireFormProps =
  EnableUmpireFormOwnProps &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

const EnableUmpireForm: React.SFC<EnableUmpireFormProps> = ({
  open,
  onSubmit,
  onCancel,
  submitForm,
  project,
}) => {
  const initialValues = {
    umpirePort: project.umpirePort || 8080,
  };
  const hasExisting = project.hasExistingUmpire;
  return (
    <Dialog open={open} onClose={onCancel}>
      <DialogTitle>Enable Umpire</DialogTitle>
      <DialogContent>
        <InnerForm
          onSubmit={onSubmit}
          initialValues={initialValues}
          projectName={project.name}
          hasExisting={hasExisting}
        />
      </DialogContent>
      <DialogActions>
        <Button color="primary" onClick={submitForm}>
          {hasExisting ? 'Add' : 'Create'}
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
};

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(ENABLE_UMPIRE_FORM);

const mapStateToProps = (state: RootState) => ({
  open: isFormVisible(state),
});

const mapDispatchToProps = {
  submitForm: () => submit(ENABLE_UMPIRE_FORM),
};

export default connect(mapStateToProps, mapDispatchToProps)(EnableUmpireForm);
