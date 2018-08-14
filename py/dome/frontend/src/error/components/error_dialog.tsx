// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import {connect} from 'react-redux';

import {RootState} from '@app/types';

import {hideErrorDialog} from '../actions';
import {getErrorMessage, isErrorDialogShown} from '../selectors';

interface ErrorDialogProps {
  message: string;
  show: boolean;
  hideErrorDialog: () => any;
}

const ErrorDialog: React.SFC<ErrorDialogProps> =
  ({message, show, hideErrorDialog}) => (
    <Dialog
      open={show}
      modal={false}
      onRequestClose={hideErrorDialog}
      actions={[
        <RaisedButton key="btn" label="close" onClick={hideErrorDialog} />,
      ]}
    >
      <div>
        An error has occured, please copy the following error message, and
        contact the ChromeOS factory team.
      </div>
      {/* wrap the textarea with a div, otherwise, setting the width of
              textarea as 100% will make it overflow */}
      <div>
        <textarea
          disabled
          style={{width: '100%', height: '10em'}}
          value={message}
        />
      </div>
    </Dialog>
  );

const mapStateToProps = (state: RootState) => ({
  show: isErrorDialogShown(state),
  message: getErrorMessage(state),
});

const mapDispatchToProps = {hideErrorDialog};

export default connect(mapStateToProps, mapDispatchToProps)(ErrorDialog);
