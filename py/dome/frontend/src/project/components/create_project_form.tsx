// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import {Field, InjectedFormProps, reduxForm} from 'redux-form';

import {renderTextField, validateRequired} from '@common/form';

import {CREATE_PROJECT_FORM} from '../constants';

export interface CreateProjectFormData {
  name: string;
}

interface CreateProjectFormProps {
  projectNames: string[];
}

class CreateProjectForm extends React.Component<
  CreateProjectFormProps
  & InjectedFormProps<CreateProjectFormData, CreateProjectFormProps>> {

  validateUnique = (value: string) => {
    return this.props.projectNames.includes(value) ?
      `${value} already exist` : undefined;
  }

  render() {
    const {handleSubmit} = this.props;
    return (
      <form onSubmit={handleSubmit}>
        <Field
          name="name"
          label="New project name"
          validate={[
            validateRequired,
            this.validateUnique,
          ]}
          component={renderTextField}
        />
        <RaisedButton
          label="CREATE A NEW PROJECT"
          primary={true}
          fullWidth={true}
          type="submit"
        />
      </form>);
  }
}

export default reduxForm<CreateProjectFormData, CreateProjectFormProps>({
  form: CREATE_PROJECT_FORM,
})(CreateProjectForm);
