// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import Dialog from '@material-ui/core/Dialog';
import DialogActions from '@material-ui/core/DialogActions';
import DialogContent from '@material-ui/core/DialogContent';
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
    <Dialog open={show} onClose={hideErrorDialog}>
      <DialogContent>
        An error has occured, please copy the following error message, and
        contact the ChromeOS factory team.
        <textarea
          disabled
          style={{width: '100%', height: '10em'}}
          value={message}
        />
      </DialogContent>
      <DialogActions>
        <Button color="primary" onClick={hideErrorDialog}>
          close
        </Button>
      </DialogActions>
    </Dialog>
  );

const mapStateToProps = (state: RootState) => ({
  show: isErrorDialogShown(state),
  message: getErrorMessage(state),
});

const mapDispatchToProps = {hideErrorDialog};

export default connect(mapStateToProps, mapDispatchToProps)(ErrorDialog);
