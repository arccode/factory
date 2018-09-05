// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import CircularProgress from '@material-ui/core/CircularProgress';
import Modal from '@material-ui/core/Modal';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import React from 'react';
import {connect} from 'react-redux';

import {RootState} from '@app/types';

import {testAuthToken, tryLogin} from '../actions';
import {isLoggedIn} from '../selectors';
import {AuthData} from '../types';

import LoginForm from './login_form';

const styles = (theme: Theme) => createStyles({
  root: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
});

interface LoginAppProps extends WithStyles<typeof styles> {
  isLoggedIn: boolean | null;
  tryLogin: (values: AuthData) => any;
  testAuthToken: () => any;
}

class LoginApp extends React.Component<LoginAppProps> {
  componentDidMount() {
    this.props.testAuthToken();
  }

  render() {
    const {isLoggedIn, classes, tryLogin} = this.props;
    if (isLoggedIn === null) {
      return (
        <Modal open disableAutoFocus className={classes.root}>
          <CircularProgress size={120} />
        </Modal>
      );
    }
    return (
      <LoginForm onSubmit={tryLogin} />
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  isLoggedIn: isLoggedIn(state),
});

const mapDispatchToProps = {testAuthToken, tryLogin};

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(LoginApp));
