// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import IconButton from '@material-ui/core/IconButton';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import Tooltip from '@material-ui/core/Tooltip';
import Typography from '@material-ui/core/Typography';
import CreateNewFolderIcon from '@material-ui/icons/CreateNewFolder';
import NoteAddIcon from '@material-ui/icons/NoteAdd';
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

const styles = (theme: Theme) => createStyles({
  header: {
    display: 'flex',
    alignItems: 'center',
  },
  headerButtonGroup: {
    display: 'flex',
    justifyContent: 'flex-end',
    width: '100%',
  },
});

interface ParameterState {
  currentDirId: number | null;
}

type ParameterAppProps =
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

class ParameterApp extends React.Component<ParameterAppProps, ParameterState> {

  state = {currentDirId: null};

  setCurrentDirId = (id: number | null) => {
    this.setState({currentDirId: id});
  }

  render() {
    const {currentDirId} = this.state;
    const {classes} = this.props;
    return (
      <>
        <UpdateParameterDialog />
        <CreateDirectoryForm dirId={currentDirId}/>
        <Card>
          <CardContent className={classes.header}>
            <Typography variant="headline">Parameter</Typography>
            <div className={classes.headerButtonGroup}>
              <Tooltip title="Create Files">
                <IconButton
                  color="primary"
                  onClick={() => this.props.updateComponent(
                    this.state.currentDirId, 'unused_name', true)}
                >
                  <NoteAddIcon />
                </IconButton>
              </Tooltip>
              <Tooltip title="Add directory">
                <IconButton
                  color="primary"
                  onClick={this.props.createDirectory}
                >
                  <CreateNewFolderIcon />
                </IconButton>
              </Tooltip>
            </div>
          </CardContent>
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

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(ParameterApp));
