// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import dateFormat from 'dateformat';
import React from 'react';
import {connect} from 'react-redux';
import {
  Field,
  InjectedFormProps,
  reduxForm,
  submit,
} from 'redux-form';

import formDialog from '@app/form_dialog';
import project from '@app/project';
import {RootState} from '@app/types';
import FileUploadDialog from '@common/components/file_upload_dialog';
import {renderTextField, validateRequired} from '@common/form';

import {startUpdateResource} from '../actions';
import {UPDATE_RESOURCE_FORM} from '../constants';
import {
  UpdateResourceFormPayload,
  UpdateResourceRequestPayload,
} from '../types';

interface FormData {
  name: string;
  note: string;
}

const InnerFormComponent: React.SFC<InjectedFormProps<FormData>> =
  ({handleSubmit}) => (
    <form onSubmit={handleSubmit}>
      <Field
        name="name"
        label="New Bundle Name"
        validate={validateRequired}
        component={renderTextField}
      />
      <Field name="note" label="Note" component={renderTextField} />
    </form>
  );

const InnerForm = reduxForm<FormData>({
  form: UPDATE_RESOURCE_FORM,
})(InnerFormComponent);

interface UpdateResourceFormProps {
  open: boolean;
  submitForm: () => any;
  cancelUpdate: () => any;
  startUpdate: (name: string, data: UpdateResourceRequestPayload) => any;
  project: string;
  payload: UpdateResourceFormPayload;
}

interface UpdateResourceFormStates {
  initialValues: Partial<FormData>;
}

class UpdateResourceForm
  extends React.Component<UpdateResourceFormProps, UpdateResourceFormStates> {
  state = {
    initialValues: {},
  };

  static getDerivedStateFromProps(
    props: UpdateResourceFormProps, state: UpdateResourceFormStates) {
    // replace the timestamp in the old bundle name with current timestamp
    const {project, payload: {bundleName, resourceType}} = props;
    const regexp = /\d{14}$/;
    const note = `Updated "${resourceType}" type resource`;
    let name = bundleName;
    const timeString = dateFormat(new Date(), 'yyyymmddHHMMss');
    if (regexp.test(bundleName)) {
      name = bundleName.replace(regexp, timeString);
    } else {
      if (name === 'empty') {
        name = project;
      }
      name += '-' + timeString;
    }
    return {initialValues: {name, note}};
  }

  handleCancel = () => {
    this.props.cancelUpdate();
  }

  handleSubmit = ({name, note, file}: FormData & {file: File}) => {
    const {
      project,
      startUpdate,
      payload: {bundleName, resourceKey, resourceType},
    } = this.props;
    const data = {
      project,
      name: bundleName,
      newName: name,
      note,
      resources: {
        [resourceType]: {
          // TODO(pihsun): This should not be needed.
          type: resourceType,
          file,
        },
      },
    };
    startUpdate(resourceKey, data);
  }

  render() {
    const {open, submitForm} = this.props;
    return (
      <FileUploadDialog<FormData>
        open={open}
        title="Update Resource"
        onCancel={this.handleCancel}
        onSubmit={this.handleSubmit}
        submitForm={submitForm}
      >
        <InnerForm initialValues={this.state.initialValues} />
      </FileUploadDialog>
    );
  }
}

const isFormVisible =
  formDialog.selectors.isFormVisibleFactory(UPDATE_RESOURCE_FORM);
const getFormPayload =
  formDialog.selectors.getFormPayloadFactory(UPDATE_RESOURCE_FORM);

const mapStateToProps = (state: RootState) => ({
  open: isFormVisible(state),
  project: project.selectors.getCurrentProject(state),
  payload: getFormPayload(state)!,
});

const mapDispatchToProps = {
  startUpdate: startUpdateResource,
  cancelUpdate: () => formDialog.actions.closeForm(UPDATE_RESOURCE_FORM),
  submitForm: () => submit(UPDATE_RESOURCE_FORM),
};

export default connect(
  mapStateToProps, mapDispatchToProps)(UpdateResourceForm);
