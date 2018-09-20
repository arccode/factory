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
  Field,
  formValueSelector,
  InjectedFormProps,
  reduxForm,
  submit,
  WrappedFieldProps,
} from 'redux-form';

import formDialog from '@app/form_dialog';
import {Project} from '@app/project/types';
import {RootState} from '@app/types';
import ReduxFormTextField from '@common/components/redux_form_text_field';
import {HiddenSubmitButton, parseNumber} from '@common/form';

import {ENABLE_UMPIRE_FORM} from '../constants';

const renderAddExistingHint =
  ({input: {value, onChange}}: WrappedFieldProps) => (
    <div style={{textAlign: 'center', marginTop: 24}}>
      {value ?
        <>
          If you had not set up the Umpire Docker container, you should
          {' '}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              onChange(false);
            }}
          >
            create a new one
          </a>.
        </> :
        <>
          If you had manually set up the Umpire Docker container, you can
          {' '}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              onChange(true);
            }}
          >
            add the existing one
          </a>.
        </>
      }
    </div>);

interface FormData {
  umpirePort: number;
  umpireAddExistingOne: boolean;
}

const InnerFormComponent: React.SFC<InjectedFormProps<FormData>> =
  ({handleSubmit}) => (
    <form onSubmit={handleSubmit}>
      <ReduxFormTextField
        name="umpirePort"
        label="port"
        type="number"
        parse={parseNumber}
      />
      <Field name="umpireAddExistingOne" component={renderAddExistingHint} />
      <HiddenSubmitButton />
    </form>
  );

const InnerForm = reduxForm<FormData>({
  form: ENABLE_UMPIRE_FORM,
})(InnerFormComponent);

interface EnableUmpireFormProps {
  addExisting: boolean;
  open: boolean;
  project: Project;
  submitForm: () => any;
  onCancel: () => any;
  onSubmit: (values: FormData) => any;
}

const EnableUmpireForm: React.SFC<EnableUmpireFormProps> = ({
  open,
  onSubmit,
  onCancel,
  submitForm,
  addExisting,
  project,
}) => {
  const initialValues = {
    umpirePort: project.umpirePort || 8080,
    umpireAddExistingOne: false,
  };
  return (
    <Dialog open={open} onClose={onCancel}>
      <DialogTitle>
        {addExisting ?
            'Add Existing Umpire Instance' :
            'Create Umpire Instance'}
      </DialogTitle>
      <DialogContent>
        <InnerForm
          onSubmit={onSubmit}
          initialValues={initialValues}
        />
      </DialogContent>
      <DialogActions>
        <Button color="primary" onClick={submitForm}>
          {addExisting ? 'Add' : 'Create'}
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
};

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(ENABLE_UMPIRE_FORM);
const formValue = formValueSelector(ENABLE_UMPIRE_FORM);

const mapStateToProps = (state: RootState) => ({
  open: isFormVisible(state),
  addExisting: formValue(state, 'umpireAddExistingOne') as boolean || false,
});

const mapDispatchToProps = {
  submitForm: () => submit(ENABLE_UMPIRE_FORM),
};

export default connect(mapStateToProps, mapDispatchToProps)(EnableUmpireForm);
