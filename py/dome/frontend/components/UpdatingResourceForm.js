// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import DateAndTime from 'date-and-time';
import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import TextField from 'material-ui/TextField';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import BundlesActions from '../actions/bundlesactions';
import DomeActions from '../actions/domeactions';
import FormNames from '../constants/FormNames';

const _NAME_INPUT_VALUE_ERROR_TEST = 'This field is required';

class UpdatingResourceForm extends React.Component {
  static propTypes = {
    project: PropTypes.string.isRequired,

    show: PropTypes.bool.isRequired,

    startUpdating: PropTypes.func.isRequired,
    cancelUpdating: PropTypes.func.isRequired,

    // name of the source bundle to update
    bundleName: PropTypes.string,
    // key and type of the resource in source bundle to update
    resourceKey: PropTypes.string,
    resourceType: PropTypes.string,
  };

  state = {
    dialogOpened: false,
    nameInputValue: '',
    noteInputValue: '',
  };

  handleFileChange = () => {
    this.setState({dialogOpened: true});
  };

  handleConfirm = () => {
    if (this.state.nameInputValue == '') {
      // TODO: Chinese support
      this.setState({nameInputErrorText: _NAME_INPUT_VALUE_ERROR_TEST});
      return;
    }

    const resourceType = this.props.resourceType;
    const data = {
      project: this.props.project,
      name: this.props.bundleName,
      note: this.state.noteInputValue,
      resources: {
        [resourceType]: {
          'type': resourceType,
          'file': this.fileInput.files[0],
        },
      },
    };
    data['newName'] = this.state.nameInputValue;

    this.props.startUpdating(this.props.resourceKey, data);
  };

  handleCancel = () => {
    this.props.cancelUpdating();
  };

  // TODO(pihsun): Don't use this unrecommended method.
  // eslint-disable-next-line camelcase
  UNSAFE_componentWillReceiveProps(nextProps) {
    // the form was hidden but about to be visible
    if (nextProps.show && !this.props.show) {
      // reset file input and text fields
      this.formElement.reset();

      // replace the timestamp in the old bundle name with current timestamp
      const regexp = /\d{14}$/;
      let newBundleName = nextProps.bundleName;
      const timeString = DateAndTime.format(new Date(), 'YYYYMMDDHHmmss');
      if (regexp.test(nextProps.bundleName)) {
        newBundleName = nextProps.bundleName.replace(regexp, timeString);
      } else {
        if (newBundleName == 'empty') {
          newBundleName = nextProps.project;
        }
        newBundleName += '-' + timeString;
      }
      this.setState({
        nameInputValue: newBundleName,
        noteInputValue: `Updated "${nextProps.resourceType}" type resource`,
      });

      // bring up the file dialog
      this.fileInput.click();
    } else if (!nextProps.show && this.props.show) {
      // the form was visible but about to be hidden
      this.setState({dialogOpened: false});
    }
  }

  render() {
    return (
      <form ref={(c) => this.formElement = c}>
        <input
          className='hidden'
          type='file'
          onChange={this.handleFileChange}
          ref={(c) => this.fileInput = c}
        />
        <Dialog
          title='Update Resource'
          open={this.state.dialogOpened}
          modal={false}
          onRequestClose={this.handleCancel}
          actions={[
            <RaisedButton label='confirm' key='confirm'
              onClick={this.handleConfirm} />,
            <RaisedButton label='cancel' key='cancel'
              onClick={this.handleCancel} />,
          ]}
        >
          <TextField
            floatingLabelText='New Bundle Name'
            errorText={this.state.nameInputErrorText}
            value={this.state.nameInputValue}
            onChange={(c) => this.setState({nameInputValue: c.target.value})}
          /><br />
          <TextField
            floatingLabelText='Note'
            value={this.state.noteInputValue}
            onChange={(c) => this.setState({noteInputValue: c.target.value})}
          />
        </Dialog>
      </form>
    );
  }
}

function mapStateToProps(state) {
  return {
    project: state.getIn(['dome', 'currentProject']),
    show: state.getIn([
      'dome', 'formVisibility', FormNames.UPDATING_RESOURCE_FORM,
    ], false),
    bundleName: state.getIn([
      'dome', 'formPayload', FormNames.UPDATING_RESOURCE_FORM, 'bundleName',
    ]),
    resourceKey: state.getIn([
      'dome', 'formPayload', FormNames.UPDATING_RESOURCE_FORM, 'resourceKey',
    ]),
    resourceType: state.getIn([
      'dome', 'formPayload', FormNames.UPDATING_RESOURCE_FORM, 'resourceType',
    ]),
  };
}

function mapDispatchToProps(dispatch) {
  return {
    startUpdating: (resourceKey, data) => (
      dispatch(BundlesActions.startUpdatingResource(resourceKey, data))
    ),
    cancelUpdating: () => (
      dispatch(DomeActions.closeForm(FormNames.UPDATING_RESOURCE_FORM))
    ),
  };
}

export default connect(
    mapStateToProps, mapDispatchToProps)(UpdatingResourceForm);
