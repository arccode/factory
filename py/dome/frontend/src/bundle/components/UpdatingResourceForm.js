// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import DateAndTime from 'date-and-time';
import Immutable from 'immutable';
import FlatButton from 'material-ui/FlatButton';
import TextField from 'material-ui/TextField';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {fieldPropTypes, formPropTypes, submit} from 'redux-form';
import {Field, reduxForm} from 'redux-form/immutable';

import FileUploadDialog from '../../common/components/FileUploadDialog';
import {closeForm} from '../../formDialog/actions';
import * as actions from '../actions';
import {UPDATING_RESOURCE_FORM} from '../constants';

const nonEmpty = (value) =>
    value && value.length ? undefined : 'Can not be empty';

// TODO(pihsun): Refactor and move common form components out, so it can be
// reused by different forms.
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
    // name of the source bundle to update
    bundleName: PropTypes.string,
    // key and type of the resource in source bundle to update
    resourceKey: PropTypes.string,
    resourceType: PropTypes.string,
  };

  state = {
    initialValues: {},
  }

  static getDerivedStateFromProps(props, state) {
    // replace the timestamp in the old bundle name with current timestamp
    const {bundleName, resourceType, project} = props;
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
    const {
      project,
      bundleName,
      resourceKey,
      resourceType,
      startUpdating,
    } = this.props;
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

const mapStateToProps = (state) => {
  return {
    open: state.getIn(
        ['formDialog', 'visibility', UPDATING_RESOURCE_FORM], false),
    project: state.getIn(['project', 'currentProject']),
    ...state.getIn(
        ['formDialog', 'payload', UPDATING_RESOURCE_FORM],
        Immutable.Map()).toJS(),
  };
};

const mapDispatchToProps = (dispatch) => {
  return {
    startUpdating: (resourceKey, data) => (
      dispatch(actions.startUpdatingResource(resourceKey, data))
    ),
    cancelUpdating: () => dispatch(closeForm(UPDATING_RESOURCE_FORM)),
    submitForm: () => dispatch(submit(UPDATING_RESOURCE_FORM)),
  };
};

export default connect(
    mapStateToProps, mapDispatchToProps)(UpdatingResourceForm);
