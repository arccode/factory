// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import Checkbox from 'material-ui/Checkbox';
import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import TextField from 'material-ui/TextField';

import BundlesActions from '../actions/bundlesactions';
import DomeActions from '../actions/domeactions';
import FormNames from '../constants/FormNames';

var _NAME_INPUT_VALUE_ERROR_TEST =
    'This field is required if inplace updating is unchecked';

var UpdatingResourceForm = React.createClass({
  propTypes: {
    board: React.PropTypes.string.isRequired,

    show: React.PropTypes.bool.isRequired,

    startUpdating: React.PropTypes.func.isRequired,
    cancelUpdating: React.PropTypes.func.isRequired,

    // name of the source bundle to update
    bundleName: React.PropTypes.string,
    // type of the resource in source bundle to update
    resourceType: React.PropTypes.string
  },

  handleFileChange() {
    this.setState({dialogOpened: true});
  },

  handleCheck(event, checked) {
    this.setState({
      isInPlaceUpdate: checked,

      // Whether inplace updating is checked or not, the name input error text
      // should always be cleared. If it's unchecked -> checked, name doesn't
      // matter; if it's checked -> unchecked, the error text should already be
      // empty, and thus no hard to clear it again.
      nameInputErrorText: ''
    });
  },

  handleConfirm() {
    if (!this.state.isInPlaceUpdate && this.state.nameInputValue == '') {
      // TODO: Chinese support
      this.setState({nameInputErrorText: _NAME_INPUT_VALUE_ERROR_TEST});
      return;
    }

    var data = {
      // TODO(littlecvr): should use CamelCased
      board:  this.props.board,
      is_inplace_update:  this.state.isInPlaceUpdate,
      src_bundle_name:  this.props.bundleName,
      dst_bundle_name:  this.state.nameInputValue,
      note:  this.state.noteInputValue,
      resource_type:  this.props.resourceType,
      resource_file:  this.fileInput.files[0]
    };
    this.props.startUpdating(data);
  },

  handleCancel() {
    this.props.cancelUpdating();
  },

  getInitialState() {
    return {
      dialogOpened: false,
      isInPlaceUpdate: false,
      nameInputValue: '',
      noteInputValue: ''
    };
  },

  componentWillReceiveProps(nextProps) {
    if (nextProps.show && !this.props.show) {
      // reset file input and text fields
      this.formElement.reset();
      this.setState({
        isInPlaceUpdate: false,
        nameInputValue: '',
        noteInputValue: ''
      });
      this.fileInput.click();
    }
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
          <Checkbox
            label="in-place update"
            checked={this.state.isInPlaceUpdate}
            onCheck={this.handleCheck}
          />
          <TextField
            floatingLabelText="New Bundle Name"
            disabled={this.state.isInPlaceUpdate}
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
    board: state.getIn(['dome', 'currentBoard']),
    show: state.getIn([
      'dome', 'formVisibility', FormNames.UPDATING_RESOURCE_FORM
    ], false),
    bundleName: state.getIn([
      'dome', 'formPayload', FormNames.UPDATING_RESOURCE_FORM, 'bundleName'
    ]),
    resourceType: state.getIn([
      'dome', 'formPayload', FormNames.UPDATING_RESOURCE_FORM, 'resourceType'
    ])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    startUpdating:
        data => dispatch(BundlesActions.startUpdatingResource(data)),
    cancelUpdating: () =>
        dispatch(DomeActions.closeForm(FormNames.UPDATING_RESOURCE_FORM))
  };
}

export default connect(
    mapStateToProps, mapDispatchToProps)(UpdatingResourceForm);
