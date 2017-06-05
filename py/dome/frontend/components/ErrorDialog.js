// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import TextField from 'material-ui/TextField';

import DomeActions from '../actions/domeactions';

var ErrorDialog = React.createClass({
  propTypes: {
    message: React.PropTypes.string,
    show: React.PropTypes.bool.isRequired
  },

  handleClose() {
    this.props.hideErrorDialog();
  },

  render() {
    return (
      <Dialog
        open={this.props.show}
        modal={false}
        onRequestClose={this.handleCancel}
        actions={[
          <RaisedButton label="close" onTouchTap={this.handleClose} />,
        ]}
      >
        <div>
          An error has occured, please copy the following error message, and
          contact the ChromeOS factory team.
        </div>
        {/* wrap the textarea with a div, otherwise, setting the width of
            textarea as 100% will make it overflow */}
        <div><textarea
          ref={e => {this.textareaElement = e}}
          disabled={true}
          style={{width: '100%', height: '10em'}}
          value={this.props.message}
        ></textarea></div>
      </Dialog>
    );
  }
});

function mapStateToProps(state) {
  return {
    show: state.getIn(['dome', 'errorDialog', 'show'], false),
    message: state.getIn(['dome', 'errorDialog', 'message'], '')
  };
}

function mapDispatchToProps(dispatch) {
  return {
    hideErrorDialog: () => dispatch(DomeActions.hideErrorDialog())
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(ErrorDialog);
