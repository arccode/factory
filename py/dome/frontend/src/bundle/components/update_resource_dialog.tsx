// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import dateFormat from 'dateformat';
import React from 'react';
import {connect} from 'react-redux';
import {submit} from 'redux-form';

import formDialog from '@app/form_dialog';
import project from '@app/project';
import {RootState} from '@app/types';

import FileUploadDialog from '@common/components/file_upload_dialog';
import {DispatchProps} from '@common/types';

import {startUpdateResource} from '../actions';
import {UPDATE_RESOURCE_FORM} from '../constants';
import {getBundleNames} from '../selectors';

import UpdateResourceForm, {
  UpdateResourceFormData,
} from './update_resource_form';

type UpdateResourceDialogProps =
  ReturnType<typeof mapStateToProps> & DispatchProps<typeof mapDispatchToProps>;

interface UpdateResourceDialogStates {
  initialValues: Partial<UpdateResourceFormData>;
}

class UpdateResourceDialog extends React.Component<
  UpdateResourceDialogProps, UpdateResourceDialogStates> {
  state = {
    initialValues: {},
  };

  static getDerivedStateFromProps(
    props: UpdateResourceDialogProps, state: UpdateResourceDialogStates) {
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

  handleSubmit = (
    {name, note, file}: UpdateResourceFormData & {file: File}) => {
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
    const {open, submitForm, bundleNames} = this.props;
    return (
      <FileUploadDialog<UpdateResourceFormData>
        open={open}
        title="Update Resource"
        onCancel={this.handleCancel}
        onSubmit={this.handleSubmit}
        submitForm={submitForm}
      >
        <UpdateResourceForm
          initialValues={this.state.initialValues}
          bundleNames={bundleNames}
        />
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
  bundleNames: getBundleNames(state),
});

const mapDispatchToProps = {
  startUpdate: startUpdateResource,
  cancelUpdate: () => formDialog.actions.closeForm(UPDATE_RESOURCE_FORM),
  submitForm: () => submit(UPDATE_RESOURCE_FORM),
};

export default connect(
  mapStateToProps, mapDispatchToProps)(UpdateResourceDialog);
