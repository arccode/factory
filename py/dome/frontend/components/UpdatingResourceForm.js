// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import Checkbox from 'material-ui/Checkbox';
import DateAndTime from 'date-and-time';
import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import TextField from 'material-ui/TextField';

import BundlesActions from '../actions/bundlesactions';
import DomeActions from '../actions/domeactions';
import FormNames from '../constants/FormNames';

var _NAME_INPUT_VALUE_ERROR_TEST = 'This field is required';

var UpdatingResourceForm = React.createClass({
  propTypes: {
    project: React.PropTypes.string.isRequired,

    show: React.PropTypes.bool.isRequired,

    startUpdating: React.PropTypes.func.isRequired,
    cancelUpdating: React.PropTypes.func.isRequired,

    // name of the source bundle to update
    bundleName: React.PropTypes.string,
    // key and type of the resource in source bundle to update
    resourceKey: React.PropTypes.string,
    resourceType: React.PropTypes.string
  },

  handleFileChange() {
    this.setState({dialogOpened: true});
  },

  handleConfirm() {
    if (this.state.nameInputValue == '') {
      // TODO: Chinese support
      this.setState({nameInputErrorText: _NAME_INPUT_VALUE_ERROR_TEST});
      return;
    }

    let resourceType = this.props.resourceType;
    let data = {
      project:  this.props.project,
      name:  this.props.bundleName,
      note:  this.state.noteInputValue,
      resources: {
        [resourceType]: {
          'type': resourceType,
          'file': this.fileInput.files[0]
        }
      }
    };
    data['newName'] = this.state.nameInputValue;

    this.props.startUpdating(this.props.resourceKey, data);
  },

  handleCancel() {
    this.props.cancelUpdating();
  },

  getInitialState() {
    return {
      dialogOpened: false,
      nameInputValue: '',
      noteInputValue: ''
    };
  },

  componentWillReceiveProps(nextProps) {
    // the form was hidden but about to be visible
    if (nextProps.show && !this.props.show) {
      // reset file input and text fields
      this.formElement.reset();

      // replace the timestamp in the old bundle name with current timestamp
      let regexp = /\d{14}$/;
      let newBundleName = nextProps.bundleName;
      let timeString = DateAndTime.format(new Date(), 'YYYYMMDDHHmmss');
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
        noteInputValue: `Update ${nextProps.resourceType}`
      });

      // bring up the file dialog
      this.fileInput.click();
    }
    // the form was visible but about to be hidden
    else if (!nextProps.show && this.props.show) {
      this.setState({dialogOpened: false});
    }
  },

  render() {
    return (
      <form ref={c => this.formElement = c}>
        <input
          className="hidden"
          type="file"
          onChange={this.handleFileChange}
          ref={c => this.fileInput = c}
        />
        <Dialog
          title="Update Resource"
          open={this.state.dialogOpened}
          modal={false}
          onRequestClose={this.handleCancel}
          actions={[
            <RaisedButton label="confirm" onTouchTap={this.handleConfirm} />,
            <RaisedButton label="cancel" onTouchTap={this.handleCancel} />
          ]}
        >
          <TextField
            floatingLabelText="New Bundle Name"
            errorText={this.state.nameInputErrorText}
            value={this.state.nameInputValue}
            onChange={c => this.setState({nameInputValue: c.target.value})}
          /><br />
          <TextField
            floatingLabelText="Note"
            value={this.state.noteInputValue}
            onChange={c => this.setState({noteInputValue: c.target.value})}
          />
        </Dialog>
      </form>
    );
  }
});

function mapStateToProps(state) {
  return {
    project: state.getIn(['dome', 'currentProject']),
    show: state.getIn([
      'dome', 'formVisibility', FormNames.UPDATING_RESOURCE_FORM
    ], false),
    bundleName: state.getIn([
      'dome', 'formPayload', FormNames.UPDATING_RESOURCE_FORM, 'bundleName'
    ]),
    resourceKey: state.getIn([
      'dome', 'formPayload', FormNames.UPDATING_RESOURCE_FORM, 'resourceKey'
    ]),
    resourceType: state.getIn([
      'dome', 'formPayload', FormNames.UPDATING_RESOURCE_FORM, 'resourceType'
    ])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    startUpdating: (resourceKey, data) => dispatch(
        BundlesActions.startUpdatingResource(resourceKey, data)
    ),
    cancelUpdating: () =>
        dispatch(DomeActions.closeForm(FormNames.UPDATING_RESOURCE_FORM))
  };
}

export default connect(
    mapStateToProps, mapDispatchToProps)(UpdatingResourceForm);
