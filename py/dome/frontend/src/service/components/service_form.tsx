// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import CardActions from '@material-ui/core/CardActions';
import CardContent from '@material-ui/core/CardContent';
import React from 'react';
import {InjectedFormProps, reduxForm} from 'redux-form';

import {Schema, Service} from '../types';

import RenderFields from './render_fields';

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
        <CardContent>
          <RenderFields schema={schema} />
        </CardContent>
        <CardActions>
          <Button onClick={reset}>
            Discard Changes
          </Button>
          <Button type="submit" color="primary">
            Deploy
          </Button>
        </CardActions>
      </form>
    );
  }
}

export default reduxForm<ServiceFormData, ServiceFormProps>({})(ServiceForm);
