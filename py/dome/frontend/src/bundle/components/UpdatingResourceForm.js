// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import DateAndTime from 'date-and-time';
import Immutable from 'immutable';
import FlatButton from 'material-ui/FlatButton';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {formPropTypes, submit} from 'redux-form';
import {Field, reduxForm} from 'redux-form/immutable';
import {createStructuredSelector} from 'reselect';

import formDialog from '@app/formDialog';
import FileUploadDialog from '@common/components/FileUploadDialog';
import project from '@app/project';
import {renderTextField, validateRequired} from '@common/form';

import {startUpdatingResource} from '../actions';
import {UPDATING_RESOURCE_FORM} from '../constants';

class InnerForm extends React.Component {
  static propTypes = {...formPropTypes};

  render() {
    return (
      <form>
        <Field name='name' label='New Bundle Name' validate={validateRequired}
          component={renderTextField} />
        <Field name='note' label='Note' component={renderTextField} />
      </form>
    );
  }
}

InnerForm = reduxForm({form: UPDATING_RESOURCE_FORM})(InnerForm);

class UpdatingResourceForm extends React.Component {
  static propTypes = {
    open: PropTypes.bool.isRequired,
    submitForm: PropTypes.func.isRequired,
    cancelUpdating: PropTypes.func.isRequired,
    startUpdating: PropTypes.func.isRequired,

    project: PropTypes.string.isRequired,
    payload: PropTypes.instanceOf(Immutable.Map).isRequired,
  };

  state = {
    initialValues: {},
  }

  static getDerivedStateFromProps(props, state) {
    // replace the timestamp in the old bundle name with current timestamp
    const {project, payload} = props;
    const bundleName = payload.get('bundleName');
    const resourceType = payload.get('resourceType');
    const regexp = /\d{14}$/;
    const note = `Updated "${resourceType}" type resource`;
    let name = bundleName;
    const timeString = DateAndTime.format(new Date(), 'YYYYMMDDHHmmss');
    if (regexp.test(bundleName)) {
      name = bundleName.replace(regexp, timeString);
    } else {
      if (name === 'empty') {
        name = project;
      }
      name += '-' + timeString;
    }
    return {initialValues: {name, note}};
  }

  handleCancel = () => {
    this.props.cancelUpdating();
  }

  handleSubmit = (values) => {
    const {project, startUpdating, payload} = this.props;
    const {
      bundleName,
      resourceKey,
      resourceType,
    } = payload.toJS();
    const data = {
      project,
      name: bundleName,
      newName: values.get('name'),
      note: values.get('note'),
      resources: {
        [resourceType]: {
          type: resourceType,
          file: values.get('file'),
        },
      },
    };
    startUpdating(resourceKey, data);
  }

  render() {
    const {open, submitForm} = this.props;
    return (
      <FileUploadDialog
        title='Update Resource'
        modal={false}
        onRequestClose={this.handleCancel}
        actions={<>
          <FlatButton label='confirm' primary={true} onClick={submitForm} />
          <FlatButton label='cancel' onClick={this.handleCancel} />
        </>}
        open={open}
        onSubmit={this.handleSubmit}
      >
        <InnerForm initialValues={this.state.initialValues} />
      </FileUploadDialog>
    );
  }
}

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(UPDATING_RESOURCE_FORM);
const getFormPayload =
  formDialog.selectors.getFormPayloadFactory(UPDATING_RESOURCE_FORM);

const mapStateToProps = createStructuredSelector({
  open: isFormVisible,
  project: project.selectors.getCurrentProject,
  payload: getFormPayload,
});

const mapDispatchToProps = {
  startUpdating: startUpdatingResource,
  cancelUpdating: () => formDialog.actions.closeForm(UPDATING_RESOURCE_FORM),
  submitForm: () => submit(UPDATING_RESOURCE_FORM),
};

export default connect(
    mapStateToProps, mapDispatchToProps)(UpdatingResourceForm);
