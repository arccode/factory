// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import Card from '@material-ui/core/Card';
import CardActions from '@material-ui/core/CardActions';
import CardContent from '@material-ui/core/CardContent';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import Typography from '@material-ui/core/Typography';
import React from 'react';
import {connect} from 'react-redux';
import {InjectedFormProps, reduxForm} from 'redux-form';

import ReduxFormTextField from '@common/components/redux_form_text_field';

import {tryLogin} from '../actions';
import {AuthData} from '../types';

const styles = (theme: Theme) => createStyles({
  actions: {
    justifyContent: 'flex-end',
  },
});

type LoginFormProps =
  InjectedFormProps<AuthData> & WithStyles<typeof styles>;

const LoginForm: React.SFC<LoginFormProps> =
  ({handleSubmit, classes}) => (
    <form onSubmit={handleSubmit}>
      <Card>
        <CardContent>
          <Typography variant="headline">
            Login to continue
          </Typography>
          <ReduxFormTextField
            name="username"
            label="Username"
            type="text"
          />
          <ReduxFormTextField
            name="password"
            label="Password"
            type="password"
          />
        </CardContent>
        <CardActions className={classes.actions}>
          <Button color="primary" type="submit">Login</Button>
        </CardActions>
      </Card>
    </form>
  );

const LoginFormComponent = reduxForm<AuthData>({form: 'login'})(
  withStyles(styles)(LoginForm));

interface LoginAppProps {
  tryLogin: (values: AuthData) => any;
}

const LoginApp: React.SFC<LoginAppProps> = ({tryLogin}) => (
  <LoginFormComponent onSubmit={tryLogin} />
);

const mapDispatchToProps = {tryLogin};

export default connect(null, mapDispatchToProps)(LoginApp);
