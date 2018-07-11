// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import FlatButton from 'material-ui/FlatButton';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {Field, formPropTypes, reduxForm, submit} from 'redux-form';
import {createStructuredSelector} from 'reselect';

import formDialog from '@app/formDialog';
import project from '@app/project';
import FileUploadDialog from '@common/components/FileUploadDialog';
import {renderTextField, validateRequired} from '@common/form';

import {startUploadingBundle} from '../actions';
import {UPLOADING_BUNDLE_FORM} from '../constants';

class InnerForm extends React.Component {
  static propTypes = {...formPropTypes};

  render() {
    return (
      <form>
        <Field name="name" label="New Bundle Name" validate={validateRequired}
          component={renderTextField} />
        <Field name="note" label="New Bundle Note"
          component={renderTextField} />
      </form>
    );
  }
}

InnerForm = reduxForm({
  form: UPLOADING_BUNDLE_FORM,
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
  };

  handleCancel = () => {
    this.props.cancelUploading();
  }

  handleSubmit = ({name, note, file}) => {
    const {project, startUploading} = this.props;

    const data = {
      project,
      name,
      note,
      bundleFile: file,
    };
    startUploading(data);
  }

  render() {
    const {open, submitForm} = this.props;
    return (
      <FileUploadDialog
        title="Upload Bundle"
        open={open}
        modal={false}
        onRequestClose={this.handleCancel}
        actions={<>
          <FlatButton label="confirm" primary={true} onClick={submitForm} />
          <FlatButton label="cancel" onClick={this.handleCancel} />
        </>}
        onSubmit={this.handleSubmit}
      >
        <InnerForm />
      </FileUploadDialog>
    );
  }
}

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(UPLOADING_BUNDLE_FORM);

const mapStateToProps = createStructuredSelector({
  open: isFormVisible,
  project: project.selectors.getCurrentProject,
});

const mapDispatchToProps = {
  startUploading: startUploadingBundle,
  cancelUploading: () => formDialog.actions.closeForm(UPLOADING_BUNDLE_FORM),
  submitForm: () => submit(UPLOADING_BUNDLE_FORM),
};

export default connect(
    mapStateToProps, mapDispatchToProps)(UploadingBundleForm);
