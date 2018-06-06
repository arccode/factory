// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import RaisedButton from 'material-ui/RaisedButton';
import TextField from 'material-ui/TextField';
import PropTypes from 'prop-types';
import React from 'react';
import {fieldPropTypes} from 'redux-form';
import {Field, reduxForm} from 'redux-form/immutable';

const renderTextField = ({input, label, type}) => (
  <TextField
    floatingLabelText={label}
    type={type}
    {...input}
  />
);

renderTextField.propTypes = {
  label: PropTypes.string.isRequired,
  type: PropTypes.string.isRequired,
  ...fieldPropTypes,
};

class LoginForm extends React.Component {
  static propTypes = {
    handleSubmit: PropTypes.func.isRequired,
  };

  render() {
    const {handleSubmit} = this.props;

    return (
      <form onSubmit={handleSubmit}>
        <Field
          name='username'
          label='Username'
          component={renderTextField}
          type='text'
        />
        <br/>
        <Field
          name='password'
          label='Password'
          component={renderTextField}
          type='password'
        />
        <br/>
        <RaisedButton
          type='submit'
          label='Login'
          primary={true}
          style={{margin: 1 + 'em'}}
        />
      </form>
    );
  }
}

export default reduxForm()(LoginForm);
