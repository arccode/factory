// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import React from 'react';
import {InjectedFormProps, reduxForm} from 'redux-form';

import ReduxFormTextField from '@common/components/redux_form_text_field';
import {validateRequired} from '@common/form';

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
        <ReduxFormTextField
          name="name"
          label="New project name"
          validate={[
            validateRequired,
            this.validateUnique,
          ]}
        />
        <Button
          color="primary"
          variant="contained"
          fullWidth
          type="submit"
        >
          Create a new project
        </Button>
      </form>);
  }
}

export default reduxForm<CreateProjectFormData, CreateProjectFormProps>({
  form: CREATE_PROJECT_FORM,
})(CreateProjectForm);
