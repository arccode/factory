// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import TextField from 'material-ui/TextField';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import BundlesActions from '../actions/bundlesactions';
import DomeActions from '../actions/domeactions';
import FormNames from '../constants/FormNames';

class UploadingBundleForm extends React.Component {
  static propTypes = {
    project: PropTypes.string.isRequired,
    show: PropTypes.bool.isRequired,
    startUploading: PropTypes.func.isRequired,
    cancelUploading: PropTypes.func.isRequired,
  };

  state = {
    dialogOpened: false,
    nameInputValue: '',
    nameInputErrorText: '',
    noteInputValue: '',
  };

  handleFileChange = () => {
    this.setState({dialogOpened: true});
  };

  handleConfirm = () => {
    if (this.state.nameInputValue == '') {
      // TODO: Chinese support
      this.setState({nameInputErrorText: 'This field is required'});
      return;
    }

    const data = {
      project: this.props.project,
      name: this.state.nameInputValue,
      note: this.state.noteInputValue,
      bundleFile: this.fileInput.files[0],
    };
    this.props.startUploading(data);
  };

  handleCancel = () => {
    this.props.cancelUploading();
  };

  static getDerivedStateFromProps(props, state) {
    if (props.show !== state.lastShow) {
      const ret = {lastShow: props.show};
      if (props.show) {
        // TODO(pihsun): Consider if using redux-form for this would be better
        // than manually handling all these.
        Object.assign(ret, {
          nameInputValue: '',
          nameInputErrorText: '',
          noteInputValue: '',
        });
      } else {
        Object.assign(ret, {dialogOpened: false});
      }
      return ret;
    }
    return null;
  }

  componentDidUpdate(prevProps, prevState) {
    if (this.props.show && !prevProps.show) {
      this.formElement.reset();
      this.fileInput.click();
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
          title='Upload Bundle'
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
            floatingLabelText='New Bundle Note'
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
      'dome', 'formVisibility', FormNames.UPLOADING_BUNDLE_FORM,
    ], false),
  };
}

function mapDispatchToProps(dispatch) {
  return {
    startUploading: (data) => (
      dispatch(BundlesActions.startUploadingBundle(data))
    ),
    cancelUploading: () => (
      dispatch(DomeActions.closeForm(FormNames.UPLOADING_BUNDLE_FORM))
    ),
  };
}

export default connect(
    mapStateToProps, mapDispatchToProps)(UploadingBundleForm);
