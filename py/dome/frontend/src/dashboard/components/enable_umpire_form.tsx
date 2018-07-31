// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Dialog from 'material-ui/Dialog';
import FlatButton from 'material-ui/FlatButton';
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
import {parseNumber, renderTextField} from '@common/form';

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

interface InnerFormProps {
  addExisting: boolean;
}

interface FormData {
  umpireHost?: string;
  umpirePort: number;
  umpireAddExistingOne: boolean;
}

const InnerFormComponent: React.SFC<
  InnerFormProps & InjectedFormProps<FormData, InnerFormProps>> =
  ({handleSubmit, addExisting}) => (
    <form onSubmit={handleSubmit}>
      {/* TODO(pihsun): Dome backend doesn't support host other than
            localhost, so this can be removed. */}
      {addExisting &&
        <Field name="umpireHost" label="host" component={renderTextField} />
      }
      <Field
        name="umpirePort"
        label="port"
        type="number"
        parse={parseNumber}
        component={renderTextField}
      />
      <Field name="umpireAddExistingOne" component={renderAddExistingHint} />
    </form>
  );

const InnerForm = reduxForm<FormData, InnerFormProps>({
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
    umpireHost: project.umpireHost || 'localhost',
    umpirePort: project.umpirePort || 8080,
    umpireAddExistingOne: false,
  };
  return (
    <Dialog
      title="Enable Umpire"
      open={open}
      modal={false}
      onRequestClose={onCancel}
      actions={[<>
        <FlatButton
          label={addExisting ?
            'ADD AN EXISTING UMPIRE INSTANCE' :
            'CREATE A NEW UMPIRE INSTANCE'}
          primary={true}
          onClick={submitForm}
        />
        <FlatButton
          label="CANCEL"
          onClick={onCancel}
        />
      </>]}
    >
    <InnerForm
      addExisting={addExisting}
      onSubmit={onSubmit}
      initialValues={initialValues}
    />
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
