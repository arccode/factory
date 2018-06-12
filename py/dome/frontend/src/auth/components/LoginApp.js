// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardText, CardTitle} from 'material-ui/Card';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import * as actions from '../actions';
import LoginForm from './LoginForm';

class LoginApp extends React.Component {
  static propTypes = {
    tryLogin: PropTypes.func.isRequired,
  };

  render() {
    const {tryLogin} = this.props;
    return (
      <Card>
        <CardTitle title={'Login to continue'}></CardTitle>
        <CardText>
          <LoginForm
            form='login'
            onSubmit={tryLogin}
          />
        </CardText>
      </Card>
    );
  }
}


function mapDispatchToProps(dispatch) {
  return {
    tryLogin: (values) => dispatch(actions.tryLogin(values)),
  };
}

export default connect(null, mapDispatchToProps)(LoginApp);
