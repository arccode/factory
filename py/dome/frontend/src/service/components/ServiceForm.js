// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import RaisedButton from 'material-ui/RaisedButton';
import PropTypes from 'prop-types';
import React from 'react';
import {reduxForm} from 'redux-form/immutable';

import RenderFields from './RenderFields';

class ServiceForm extends React.Component {
  static propTypes = {
    handleSubmit: PropTypes.func.isRequired,
    schema: PropTypes.object.isRequired,
    reset: PropTypes.func.isRequired,
  };

  render() {
    const {
      handleSubmit,
      schema,
      reset,
    } = this.props;

    return (
      <form onSubmit={handleSubmit}>
        <RenderFields
          schema={schema}
        />
        <RaisedButton
          label="Discard Changes"
          onClick={reset}
          style={{margin: '1em'}}
        />
        <RaisedButton
          type="submit"
          label="Deploy"
          primary={true}
          style={{margin: '1em'}}
        />
      </form>
    );
  }
}

export default reduxForm()(ServiceForm);
