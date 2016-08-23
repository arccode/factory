// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import TextField from 'material-ui/TextField';

import Actions from '../actions/bundles';
import FormNames from '../constants/FormNames';

var UploadingBundleForm = React.createClass({
  propTypes: {
    show: React.PropTypes.bool.isRequired,
    startUploading: React.PropTypes.func.isRequired,
    cancelUploading: React.PropTypes.func.isRequired
  },

  handleFileChange() {
    this.setState({dialogOpened: true});
  },

  handleConfirm() {
    if (this.state.nameInputValue == '') {
      // TODO: Chinese support
      this.setState({nameInputErrorText: 'This field is required'});
      return;
    }

    var formData = new FormData();
    formData.append('board', this.props.board);
    formData.append('name', this.state.nameInputValue);
    formData.append('note', this.state.noteInputValue);
    formData.append('bundle_file', this.fileInput.files[0]);
    this.props.startUploading(formData);
  },

  handleCancel() {
    this.props.cancelUploading();
  },

  getInitialState() {
    return {
      dialogOpened: false,
      nameInputValue: '',
      nameInputErrorText: '',
      noteInputValue: ''
    };
  },

  componentWillReceiveProps(nextProps) {
    if (nextProps.show && !this.props.show) {
      // reset file input and text fields
      this.formElement.reset();
      this.setState({
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
          title="Upload Bundle"
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
            floatingLabelText="New Bundle Note"
            value={this.state.noteInputValue}
            onChange={c => this.setState({noteInputValue: c.target.value})}
          />
        </Dialog>
      </form>
    );
  }
});

function mapStateToProps(state, ownProps) {
  return {
    board: state.getIn(['dome', 'currentBoard']),
    show: state.getIn([
        'bundles', 'formVisibility', FormNames.UPLOADING_BUNDLE_FORM], false)
  };
}

function mapDispatchToProps(dispatch) {
  return {
    startUploading:
        formData => dispatch(Actions.startUploadingBundle(formData)),
    cancelUploading:
        () => dispatch(Actions.closeForm(FormNames.UPLOADING_BUNDLE_FORM))
  };
}

export default connect(
    mapStateToProps, mapDispatchToProps)(UploadingBundleForm);
