// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import Card from '@material-ui/core/Card';
import CardActions from '@material-ui/core/CardActions';
import CardContent from '@material-ui/core/CardContent';
import CardHeader from '@material-ui/core/CardHeader';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';
import {RootState} from '@app/types';
import {DispatchProps} from '@common/types';

import {CREATE_DIRECTORY_FORM, UPDATE_PARAMETER_FORM} from '../constants';
import {getLoadingStatus} from '../selector';

import CreateDirectoryForm from './create_directory_form';
import ParameterList from './parameter_list';
import UpdateParameterDialog from './update_parameter_dialog';

interface ParameterState {
  currentDirId: number | null;
}

type ParameterAppProps =
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

class ParameterApp extends React.Component<ParameterAppProps, ParameterState> {

  state = {currentDirId: null};

  setCurrentDirId = (id: number | null) => {
    this.setState({currentDirId: id});
  }

  render() {
    const {currentDirId} = this.state;
    return (
      <>
        <UpdateParameterDialog />
        <CreateDirectoryForm dirId={currentDirId}/>
        <Card>
          <CardHeader title="Parameter" />
          <CardActions>
            <Button
              variant="outlined"
              onClick={() => this.props.updateComponent(
                this.state.currentDirId, 'unused_name', true)}
            >
              Upload file
            </Button>
            <Button
              variant="outlined"
              onClick={this.props.createDirectory}
            >
              Add directory
            </Button>
          </CardActions>
          <CardContent>
            {this.props.loading ? 'LOADING' : (
              <ParameterList
                currentDirId={currentDirId}
                dirClicked={this.setCurrentDirId}
              />
            )}
          </CardContent>
        </Card>
      </>
    );
  }

}

const mapStateToProps = (state: RootState) => ({
  loading: getLoadingStatus(state),
});

const mapDispatchToProps = {
  updateComponent:
      (dirId: number | null, name: string, multiple: boolean) =>
          (formDialog.actions.openForm(
              UPDATE_PARAMETER_FORM, {id: null, dirId, name, multiple})),
  createDirectory: () => formDialog.actions.openForm(CREATE_DIRECTORY_FORM),
};

export default connect(mapStateToProps, mapDispatchToProps)(ParameterApp);
