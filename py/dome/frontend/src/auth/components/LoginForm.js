// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import RaisedButton from 'material-ui/RaisedButton';
import PropTypes from 'prop-types';
import React from 'react';
import {Field, reduxForm} from 'redux-form';

import {renderTextField} from '@common/form';

class LoginForm extends React.Component {
  static propTypes = {
    handleSubmit: PropTypes.func.isRequired,
  };

  render() {
    const {handleSubmit} = this.props;

    return (
      <form onSubmit={handleSubmit}>
        <Field
          name="username"
          label="Username"
          component={renderTextField}
          type="text"
        />
        <br/>
        <Field
          name="password"
          label="Password"
          component={renderTextField}
          type="password"
        />
        <br/>
        <RaisedButton
          type="submit"
          label="Login"
          primary={true}
          style={{margin: '1em'}}
        />
      </form>
    );
  }
}

export default reduxForm()(LoginForm);
