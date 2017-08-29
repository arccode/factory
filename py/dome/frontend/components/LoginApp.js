// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardTitle, CardText} from 'material-ui/Card';
import {connect} from 'react-redux';
import React from 'react';
import TextField from 'material-ui/TextField';

import DomeActions from '../actions/domeactions';
import LoginForm from './LoginForm'

var LoginApp = React.createClass({
  propTypes: {
    tryLogin: React.PropTypes.func.isRequired
  },

  render() {
    const {tryLogin} = this.props;
    return (
      <Card>
        <CardTitle title={'Login to continue'}></CardTitle>
        <CardText>
          <LoginForm
            form="login"
            onSubmit={tryLogin}
          />
        </CardText>
      </Card>
    );
  }
});


function mapDispatchToProps(dispatch) {
  return {
    tryLogin: values => dispatch(DomeActions.tryLogin(values))
  };
}

export default connect(null, mapDispatchToProps)(LoginApp);
