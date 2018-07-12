// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardText, CardTitle} from 'material-ui/Card';
import React from 'react';
import {connect} from 'react-redux';

import {tryLogin} from '../actions';
import {AuthData} from '../types';

import LoginForm from './LoginForm';

interface LoginAppProps {
  tryLogin: (values: AuthData) => any;
}

const LoginApp: React.SFC<LoginAppProps> = ({tryLogin}) => (
  <Card>
    <CardTitle title="Login to continue" />
    <CardText>
      <LoginForm
        form="login"
        onSubmit={tryLogin}
      />
    </CardText>
  </Card>
);

const mapDispatchToProps = {tryLogin};

export default connect(null, mapDispatchToProps)(LoginApp);
