// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import grey from '@material-ui/core/colors/grey';
import Dialog from '@material-ui/core/Dialog';
import DialogContent from '@material-ui/core/DialogContent';
import DialogTitle from '@material-ui/core/DialogTitle';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import Typography from '@material-ui/core/Typography';
import classNames from 'classnames';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';
import {RootState} from '@app/types';

import {thinScrollBarX} from '@common/styles';
import {DispatchProps} from '@common/types';

import {fetchParameters, startUpdateComponentVersion} from '../actions';
import {UPDATE_PARAMETER_FORM} from '../constants';
import {getParameterDirs, getParameters} from '../selector';
import {Parameter} from '../types';

const styles = (theme: Theme) => createStyles({
  root: {
    display: 'grid',
    gridTemplateColumns: '1fr 2fr auto',
    width: '100%',
  },
  cell: {
    padding: theme.spacing.unit,
    display: 'flex',
    alignItems: 'center',
    borderBottom: `1px solid ${grey[300]}`,
    fontSize: theme.typography.pxToRem(13),
    ...thinScrollBarX,
  },
  ellipsis: {
    overflow: 'hidden',
    whiteSpace: 'nowrap',
    textOverflow: 'ellipsis',
  },
  actionColumn: {
    justifyContent: 'center',
  },
});

interface ParameterListState {
  currentDirId: number | null;
  openedId: number | null;
}

interface ParameterListOwnProps {
  dirClicked: (id: number) => any;
}

type ParameterListProps =
  ParameterListOwnProps &
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

class ParameterList extends
  React.Component<ParameterListProps, ParameterListState> {

  state = {currentDirId: null, openedId: null};

  handleClickDir = (dirId: number) => {
    this.setState({currentDirId: dirId});
    this.props.dirClicked(dirId);
  }

  handleclickVersion = (compId: number) => {
    this.setState({openedId: compId});
  }

  handleCloseClickVersion = () => {
    this.setState({openedId: null});
  }

  componentDidMount() {
    this.props.fetchParameters();
  }

  render() {
    const {classes, parameters, parameterDirs} = this.props;
    const {currentDirId, openedId} = this.state;
    const openedComponent = openedId == null ? null : parameters[openedId];
    const currentDir =
      currentDirId == null ? null : parameterDirs[currentDirId];
    const currentLevelDirectories = parameterDirs
      .filter((dir) => dir.parentId === currentDirId)
      .map((parameterDir) => (
        <React.Fragment key={parameterDir.id}>
          <div className={classes.cell}>
            <Button onClick={() => this.handleClickDir(parameterDir.id)}>
              {parameterDir.name}
            </Button>
          </div>
          <div className={classes.cell}>
            {parameterDir.id}
          </div>
          <div className={classes.cell}>
            {parameterDir.parentId}
          </div>
        </React.Fragment>
      ));
    const currentLevelComponents = parameters
      .filter((parameter) => parameter.dirId === currentDirId)
      .map((parameter) => (
        <React.Fragment key={parameter.id}>
          <div className={classes.cell}>
            {parameter.name} {parameter.id} {parameter.dirId}
          </div>
          <div className={classes.cell}>
            <Button onClick={() => this.handleclickVersion(parameter.id)}>
              Version
            </Button>
          </div>
          <div className={classes.cell}>
            <Button
              onClick={() => this.props.updateComponent(
                parameter.id, parameter.dirId, parameter.name, false)}
            >
              Update
            </Button>
          </div>
        </React.Fragment>
      ));
    const componentRevisions = (component: Parameter) => {
      return component.revisions.map((filePath, versionId) => {
        // Generate file name and hash from file path form:
        // {filePath}/{fileName}.{md5hash}
        const baseName = filePath.split('/').pop();
        const parts = baseName ? baseName.split('.') : undefined;
        const hash = parts ? parts.pop() : undefined;
        const fileName = parts ? parts.join('.') : undefined;
        return (
          <React.Fragment key={versionId}>
            <div className={classes.cell}>{versionId}:{fileName}</div>
            <div className={classNames(classes.cell, classes.ellipsis)}>
              {hash}
            </div>
            <div className={classes.cell}>
              <Button
                onClick={() => this.props.updateComponentVersion(
                          component.id,
                          component.name,
                          versionId)
                }
              >
                Use
              </Button>
            </div>
          </React.Fragment>
        );
      });
    };

    return (
      <div>
        <p>current dir id: {currentDirId}</p>
        <Typography variant="subheading" gutterBottom>DIRECTORIES</Typography>
        {currentDir != null &&
          <Button onClick={() => this.handleClickDir(currentDir.parentId)}>
            ..
          </Button>
        }
        <div className={classes.root}>{currentLevelDirectories}</div>
        <Typography variant="subheading" gutterBottom>FILES</Typography>
        <div className={classes.root}>{currentLevelComponents}</div>
        <Dialog
          open={this.state.openedId != null}
          onClose={this.handleCloseClickVersion}
          scroll="paper"
          aria-labelledby="scroll-dialog-title"
        >
          {
            openedComponent != null &&
            <>
              <DialogTitle id="scroll-dialog-title">
                {openedComponent.name}
              </DialogTitle>
              <DialogContent>
                <p>current version: {openedComponent.usingVer}</p>
                <div className={classes.root}>
                  {componentRevisions(openedComponent)}
                </div>
                <Button
                  onClick={this.handleCloseClickVersion}
                  color="primary"
                >
                  Close
                </Button>
              </DialogContent>
            </>
          }
        </Dialog>
      </div>
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  parameters: getParameters(state),
  parameterDirs: getParameterDirs(state),
});

const mapDispatchToProps = {
  fetchParameters,
  updateComponent:
    (id: number, dirId: number | null, name: string, multiple: boolean) =>
      formDialog.actions.openForm(
        UPDATE_PARAMETER_FORM, {id, dirId, name, multiple}),
  updateComponentVersion: (id: number, name: string, usingVer: number) =>
    startUpdateComponentVersion({id, name, usingVer}),
};

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(ParameterList));
