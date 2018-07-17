// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import {InjectedFormProps, reduxForm} from 'redux-form';

import {Schema, Service} from '../types';

import RenderFields from './RenderFields';

type ServiceFormData = Service;

interface ServiceFormProps {
  schema: Schema;
}

class ServiceForm extends React.Component<
  ServiceFormProps
  & InjectedFormProps<ServiceFormData, ServiceFormProps>> {
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

export default reduxForm<ServiceFormData, ServiceFormProps>({})(ServiceForm);
