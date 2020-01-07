// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import grey from '@material-ui/core/colors/grey';
import Dialog from '@material-ui/core/Dialog';
import DialogActions from '@material-ui/core/DialogActions';
import DialogContent from '@material-ui/core/DialogContent';
import DialogTitle from '@material-ui/core/DialogTitle';
import IconButton from '@material-ui/core/IconButton';
import List from '@material-ui/core/List';
import ListItem from '@material-ui/core/ListItem';
import ListItemIcon from '@material-ui/core/ListItemIcon';
import ListSubheader from '@material-ui/core/ListSubheader';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import Tooltip from '@material-ui/core/Tooltip';
import Typography from '@material-ui/core/Typography';
import ArrowBackIcon from '@material-ui/icons/ArrowBack';
import BorderColorIcon from '@material-ui/icons/BorderColor';
import CloudUploadIcon from '@material-ui/icons/CloudUpload';
import UpdateIcon from '@material-ui/icons/Update';
import classNames from 'classnames';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';
import {RootState} from '@app/types';

import {thinScrollBarX} from '@common/styles';
import {DispatchProps} from '@common/types';

import {fetchParameters, startUpdateComponentVersion} from '../actions';
import {
  RENAME_DIRECTORY_FORM,
  RENAME_PARAMETER_FORM,
  UPDATE_PARAMETER_FORM,
} from '../constants';
import {getParameterDirs, getParameters} from '../selector';
import {Parameter} from '../types';

import RenameDirectoryForm from './rename_directory_form';
import RenameParameterForm from './rename_parameter_form';

const styles = (theme: Theme) => createStyles({
  directoryTable: {
    display: 'grid',
    gridTemplateColumns: '1fr auto',
    width: '100%',
  },
  componentTable: {
    display: 'grid',
    gridTemplateColumns: '1fr auto auto auto',
    width: '100%',
  },
  revisionTable: {
    display: 'grid',
    gridTemplateColumns: '32px 1fr 2fr auto',
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
    gridColumn: 'span 3',
  },
  directoryLabel: {
    justifyContent: 'left',
    textTransform: 'none',
    fontWeight: theme.typography.fontWeightRegular,
  },
  padLeft: {
    paddingLeft: 24,
  },
  revisionActionColumn: {
    justifyContent: 'center',
  },
  bold: {
    fontWeight: 600,
  },
});

interface ParameterListState {
  openedComponentId: number | null;
}

interface ParameterListOwnProps {
  currentDirId: number | null;
  dirClicked: (id: number | null) => any;
}

type ParameterListProps =
  ParameterListOwnProps &
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

class ParameterList extends
  React.Component<ParameterListProps, ParameterListState> {

  state = {openedComponentId: null};

  handleClickDir = (dirId: number | null) => {
    this.props.dirClicked(dirId);
  }

  handleClickBack = (dirId: number | null) => {
    if (dirId == null) {
      return;
    }
    this.handleClickDir(this.props.parameterDirs[dirId].parentId);
  }

  handleClickVersion = (compId: number) => {
    this.setState({openedComponentId: compId});
  }

  handleCloseClickVersion = () => {
    this.setState({openedComponentId: null});
  }

  handleRenameParameter = (compId: number) => {
    this.props.renameParameter(compId, this.props.parameters[compId].name);
  }

  handleRenameDirectory = (dirId: number) => {
    this.props.renameDirectory(dirId, this.props.parameterDirs[dirId].name);
  }

  componentDidMount() {
    this.props.fetchParameters();
  }

  render() {
    const {currentDirId, classes, parameters, parameterDirs} = this.props;
    const {openedComponentId} = this.state;
    const openedComponent =
      openedComponentId == null ? null : parameters[openedComponentId];

    const getPath = (dirId: number | null): string => {
      if (dirId == null) {
        return '/';
      }
      const dir = parameterDirs[dirId];
      return `${getPath(dir.parentId)}${dir.name}/`;
    };
    const currentPath = getPath(currentDirId);

    const directoryTable = (
      <div className={classes.directoryTable}>
        <RenameDirectoryForm />
        <div className={classNames(classes.cell, classes.padLeft)}>
          <Typography variant="caption">name</Typography>
        </div>
        <div className={classNames(classes.cell)}>
          <Typography variant="caption">actions</Typography>
        </div>
        {parameterDirs
          .filter((dir) => dir.parentId === currentDirId)
          .map((parameterDir) => (
            <React.Fragment key={parameterDir.id}>
              <div className={classNames(classes.cell, classes.padLeft)}>
                <Button
                  classes={{root: classes.directoryLabel}}
                  fullWidth
                  onClick={() => this.handleClickDir(parameterDir.id)}
                >
                  {parameterDir.name}
                </Button>
              </div>
              <div className={classes.cell}>
                <Tooltip title="Rename">
                  <IconButton
                    onClick={() => this.handleRenameDirectory(parameterDir.id)}
                  >
                    <BorderColorIcon />
                  </IconButton>
                </Tooltip>
              </div>
            </React.Fragment>
          ))}
      </div>);

    const componentTable = (
      <div className={classes.componentTable}>
        <RenameParameterForm />
        <div className={classNames(classes.cell, classes.padLeft)}>
          <Typography variant="caption">name</Typography>
        </div>
        <div className={classNames(classes.cell, classes.actionColumn)}>
          <Typography variant="caption">actions</Typography>
        </div>
        {parameters
          .filter((parameter) => parameter.dirId === currentDirId)
          .map((parameter) => (
            <React.Fragment key={parameter.id}>
              <div className={classNames(classes.cell, classes.padLeft)}>
                {parameter.name}
              </div>
              <div className={classes.cell}>
                <Tooltip title="Rename">
                  <IconButton
                    onClick={() => this.handleRenameParameter(parameter.id)}
                  >
                    <BorderColorIcon />
                  </IconButton>
                </Tooltip>
              </div>
              <div className={classes.cell}>
                <Tooltip title="Versions">
                  <IconButton
                    onClick={() => this.handleClickVersion(parameter.id)}
                  >
                    <UpdateIcon />
                  </IconButton>
                </Tooltip>
              </div>
              <div className={classes.cell}>
                <Tooltip title="Update" className={classes.cell}>
                  <IconButton
                    onClick={() => this.props.updateComponent(
                      parameter.id, parameter.dirId, parameter.name, false)}
                  >
                    <CloudUploadIcon />
                  </IconButton>
                </Tooltip>
              </div>
            </React.Fragment>
          ))}
      </div>);

    // TODO(pihsun): Move revision dialog into another component.
    const revisionTable = (component: Parameter) => (
      <div className={classes.revisionTable}>
        <div className={classes.cell}>
          <Typography variant="caption">ID</Typography>
        </div>
        <div className={classes.cell}>
          <Typography variant="caption">name</Typography>
        </div>
        <div className={classes.cell}>
          <Typography variant="caption">hash</Typography>
        </div>
        <div className={classNames(classes.cell, classes.revisionActionColumn)}>
          <Typography variant="caption">actions</Typography>
        </div>
        {component.revisions.map((filePath, versionId) => {
          // Generate file name and hash from file path form:
          // {filePath}/{fileName}.{md5hash}
          const baseName = filePath.split('/').pop();
          const parts = baseName ? baseName.split('.') : undefined;
          const hash = parts ? parts.pop() : undefined;
          const fileName = parts ? parts.join('.') : undefined;
          const isUsing = component.usingVer === versionId;
          const rowClass = classNames(classes.cell, isUsing && classes.bold);
          return (
            <React.Fragment key={versionId}>
              <div className={rowClass}>{versionId}</div>
              <div className={rowClass}>{fileName}</div>
              <div className={classNames(rowClass, classes.ellipsis)}>
                {hash}
              </div>
              <div className={classes.cell}>
                <Button
                  onClick={() => this.props.updateComponentVersion(
                            component.id, component.name, versionId)}
                  color="primary"
                  fullWidth
                >
                  {isUsing ? 'Using' : 'Use'}
                </Button>
              </div>
            </React.Fragment>
          );
        })}
      </div>);

    return (
      <List>
        <ListItem disableGutters dense>
          <ListItemIcon>
            <IconButton
              onClick={() => this.handleClickBack(currentDirId)}
              disabled={currentDirId == null}
            >
              <ArrowBackIcon />
            </IconButton>
          </ListItemIcon>
          <Typography variant="subtitle1">
            Current directory: {currentPath}
          </Typography>
        </ListItem>
        <ListSubheader>Directories</ListSubheader>
        <ListItem>{directoryTable}</ListItem>
        <ListSubheader>Files</ListSubheader>
        <ListItem>{componentTable}</ListItem>

        <Dialog
          open={openedComponentId != null}
          onClose={this.handleCloseClickVersion}
        >
          {openedComponent != null &&
            <>
              <DialogTitle id="scroll-dialog-title">
                Revisions of file {openedComponent.name}
              </DialogTitle>
              <DialogContent>
                {revisionTable(openedComponent)}
              </DialogContent>
              <DialogActions>
                <Button
                  onClick={this.handleCloseClickVersion}
                  color="primary"
                >
                  Close
                </Button>
              </DialogActions>
            </>
          }
        </Dialog>
      </List>
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
  renameParameter: (id: number, name: string) =>
    formDialog.actions.openForm(RENAME_PARAMETER_FORM, {id, name}),
  renameDirectory: (id: number, name: string) =>
    formDialog.actions.openForm(RENAME_DIRECTORY_FORM, {id, name}),
};

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(ParameterList));
