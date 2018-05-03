// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {reduxForm} from 'redux-form/immutable';
import RaisedButton from 'material-ui/RaisedButton';
import RenderFields from './RenderFields';

var ServiceForm = React.createClass({
  propTypes: {
    handleSubmit: React.PropTypes.func.isRequired,
    schema: React.PropTypes.object.isRequired,
    reset: React.PropTypes.func.isRequired
  },

  render() {
    const {
      handleSubmit,
      schema,
      reset
    } = this.props;

    return (
      <form onSubmit={handleSubmit}>
        <RenderFields
          schema={schema}
        />
        <RaisedButton
          label='Discard Changes'
          onClick={reset}
          style={{margin: 1 + 'em'}}
        />
        <RaisedButton
          type='submit'
          label='Deploy'
          primary={true}
          style={{margin: 1 + 'em'}}
        />
      </form>
    );
  }
});

export default reduxForm()(ServiceForm);
