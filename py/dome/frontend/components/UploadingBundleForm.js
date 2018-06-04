// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import FlatButton from 'material-ui/FlatButton';
import TextField from 'material-ui/TextField';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {fieldPropTypes, formPropTypes, submit} from 'redux-form';
import {Field, reduxForm} from 'redux-form/immutable';

import BundlesActions from '../actions/bundlesactions';
import DomeActions from '../actions/domeactions';
import FormNames from '../constants/FormNames';

import FileUploadDialog from './FileUploadDialog';

const FORM_NAME = FormNames.UPLOADING_BUNDLE_FORM;

const nonEmpty = (value) =>
    value && value.length ? undefined : 'Can not be empty';

const renderTextField = ({input, label, meta: {error}}) => (
  <TextField
    fullWidth={true}
    floatingLabelText={label}
    errorText={error}
    {...input}
  />
);

renderTextField.propTypes = {...fieldPropTypes};

class InnerForm extends React.Component {
  static propTypes = {...formPropTypes};

  render() {
    return (
      <form>
        <Field name='name' label='New Bundle Name' validate={nonEmpty}
          component={renderTextField} />
        <Field name='note' label='New Bundle Note'
          component={renderTextField} />
      </form>
    );
  }
}

InnerForm = reduxForm({
  form: FORM_NAME,
  initialValues: {name: '', note: ''},
})(InnerForm);

class UploadingBundleForm extends React.Component {
  static propTypes = {
    open: PropTypes.bool.isRequired,
    submitForm: PropTypes.func.isRequired,
    cancelUploading: PropTypes.func.isRequired,
    startUploading: PropTypes.func.isRequired,

    project: PropTypes.string.isRequired,
  };

  state = {
    initialValues: {},
  }

  handleCancel = () => {
    this.props.cancelUploading();
  }

  handleSubmit = (values) => {
    const {project, startUploading} = this.props;

    const data = {
      project,
      name: values.get('name'),
      note: values.get('note'),
      bundleFile: values.get('file'),
    };
    startUploading(data);
  }

  render() {
    const {open, submitForm} = this.props;
    return (
      <FileUploadDialog
        title='Upload Bundle'
        open={open}
        modal={false}
        onRequestClose={this.handleCancel}
        actions={<>
          <FlatButton label='confirm' primary={true} onClick={submitForm} />
          <FlatButton label='cancel' onClick={this.handleCancel} />
        </>}
        onSubmit={this.handleSubmit}
      >
        <InnerForm />
      </FileUploadDialog>
    );
  }
}

const mapStateToProps = (state) => {
  const domeState = state.get('dome');
  return {
    open: domeState.getIn(['formVisibility', FORM_NAME], false),
    project: domeState.get('currentProject'),
  };
};

const mapDispatchToProps = (dispatch) => {
  return {
    startUploading: (data) => (
      dispatch(BundlesActions.startUploadingBundle(data))
    ),
    cancelUploading: () => dispatch(DomeActions.closeForm(FORM_NAME)),
    submitForm: () => dispatch(submit(FORM_NAME)),
  };
};

export default connect(
    mapStateToProps, mapDispatchToProps)(UploadingBundleForm);
