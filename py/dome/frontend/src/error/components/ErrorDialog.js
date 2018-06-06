// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import * as actions from '../actions';

class ErrorDialog extends React.Component {
  static propTypes = {
    message: PropTypes.string,
    show: PropTypes.bool.isRequired,
    hideErrorDialog: PropTypes.func.isRequired,
  };

  handleClose = () => {
    this.props.hideErrorDialog();
  };

  render() {
    return (
      <Dialog
        open={this.props.show}
        modal={false}
        onRequestClose={this.handleCancel}
        actions={[
          <RaisedButton key='btn' label='close' onClick={this.handleClose} />,
        ]}
      >
        <div>
          An error has occured, please copy the following error message, and
          contact the ChromeOS factory team.
        </div>
        {/* wrap the textarea with a div, otherwise, setting the width of
            textarea as 100% will make it overflow */}
        <div><textarea
          ref={(e) => this.textareaElement = e}
          disabled={true}
          style={{width: '100%', height: '10em'}}
          value={this.props.message}
        ></textarea></div>
      </Dialog>
    );
  }
}

const mapStateToProps = (state) => {
  return {
    show: state.getIn(['error', 'show'], false),
    message: state.getIn(['error', 'message'], ''),
  };
};

const mapDispatchToProps = (dispatch) => {
  return {
    hideErrorDialog: () => dispatch(actions.hideErrorDialog()),
  };
};

export default connect(mapStateToProps, mapDispatchToProps)(ErrorDialog);
