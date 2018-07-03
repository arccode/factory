// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Dialog from 'material-ui/Dialog';
import FlatButton from 'material-ui/FlatButton';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {fieldPropTypes, formPropTypes, submit} from 'redux-form';
import {Field, formValueSelector, reduxForm} from 'redux-form/immutable';
import {createStructuredSelector} from 'reselect';

import formDialog from '@app/formDialog';
import {renderTextField} from '@common/form';

import {ENABLING_UMPIRE_FORM} from '../constants';

const renderAddExistingHint = ({input: {value, onChange}}) => (
  <div style={{textAlign: 'center', marginTop: 24}}>
    {value &&
    <div>
      If you had not set up the Umpire Docker container, you should
      {' '}
      <a href='#' onClick={(e) => {
        e.preventDefault();
        onChange(false);
      }}>
        create a new one
      </a>.
    </div>}
    {!value && <div>
      If you had manually set up the Umpire Docker container, you can
      {' '}
      <a href='#' onClick={(e) => {
        e.preventDefault();
        onChange(true);
      }}>
        add the existing one
      </a>.
    </div>}
  </div>
);

renderAddExistingHint.propTypes = {...fieldPropTypes};

class InnerForm extends React.Component {
  static propTypes = {
    addExisting: PropTypes.bool.isRequired,
    ...formPropTypes,
  };

  render() {
    const {addExisting} = this.props;
    return (
      <form>
        {/* TODO(pihsun): Dome backend doesn't support host other than
            localhost, so this can be removed. */}
        {addExisting &&
          <Field name='umpireHost' label='host' component={renderTextField} />
        }
        <Field name='umpirePort' label='port' component={renderTextField} />
        <Field name='umpireAddExistingOne' component={renderAddExistingHint} />
      </form>
    );
  }
}

InnerForm = reduxForm({
  form: ENABLING_UMPIRE_FORM,
  initialValues: {
    umpireHost: 'localhost',
    umpirePort: 8080,
    umpireAddExistingOne: false,
  },
})(InnerForm);

class EnablingUmpireForm extends React.Component {
  static propTypes = {
    addExisting: PropTypes.bool.isRequired,
    open: PropTypes.bool.isRequired,
    submitForm: PropTypes.func.isRequired,
    onCancel: PropTypes.func.isRequired,
    onSubmit: PropTypes.func.isRequired,
  };

  render() {
    const {open, onSubmit, onCancel, submitForm, addExisting} = this.props;
    return (
      <Dialog
        title='Enable Umpire'
        open={open}
        modal={false}
        onRequestClose={onCancel}
        actions={[
          <FlatButton
            label={addExisting ?
                'ADD AN EXISTING UMPIRE INSTANCE' :
                'CREATE A NEW UMPIRE INSTANCE'}
            key='submit'
            primary={true}
            onClick={submitForm}
          />,
          <FlatButton
            label='CANCEL'
            key='cancel'
            onClick={onCancel}
          />,
        ]}
      >
        <InnerForm addExisting={addExisting} onSubmit={onSubmit} />
      </Dialog>
    );
  }
}

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(ENABLING_UMPIRE_FORM);
const formValue = formValueSelector(ENABLING_UMPIRE_FORM);

const mapStateToProps = createStructuredSelector({
  open: isFormVisible,
  addExisting: (state) => formValue(state, 'umpireAddExistingOne') || false,
});

const mapDispatchToProps = {
  submitForm: () => submit(ENABLING_UMPIRE_FORM),
};

export default connect(mapStateToProps, mapDispatchToProps)(EnablingUmpireForm);
