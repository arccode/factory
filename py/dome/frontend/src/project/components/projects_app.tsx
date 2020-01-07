// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import CardHeader from '@material-ui/core/CardHeader';
import Divider from '@material-ui/core/Divider';
import IconButton from '@material-ui/core/IconButton';
import List from '@material-ui/core/List';
import ListItem from '@material-ui/core/ListItem';
import ListItemSecondaryAction from '@material-ui/core/ListItemSecondaryAction';
import ListItemText from '@material-ui/core/ListItemText';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import Tooltip from '@material-ui/core/Tooltip';
import Typography from '@material-ui/core/Typography';
import DeleteIcon from '@material-ui/icons/Delete';
import React from 'react';
import {connect} from 'react-redux';
import {reset} from 'redux-form';

import {RootState} from '@app/types';

import {DispatchProps} from '@common/types';

import {
  createProject,
  deleteProject,
  fetchProjects,
  switchProject,
} from '../actions';
import {CREATE_PROJECT_FORM} from '../constants';
import {getProjects} from '../selectors';

import CreateProjectForm, {CreateProjectFormData} from './create_project_form';

const styles = (theme: Theme) => createStyles({
  center: {
    textAlign: 'center',
    justifyContent: 'center',
  },
  title: {
    textAlign: 'center',
    fontSize: theme.typography.h4.fontSize,
    fontWeight: theme.typography.fontWeightMedium,
  },
});

type ProjectAppProps =
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

class ProjectsApp extends React.Component<ProjectAppProps> {
  handleSubmit = ({name}: CreateProjectFormData) => {
    this.props.createProject(name);
    this.props.resetForm();
  }

  componentDidMount() {
    this.props.fetchProjects();
  }

  render() {
    const {classes, projects, switchProject, deleteProject} = this.props;
    const projectNames = Object.keys(projects).sort();
    return (
      <Card>
        {/* TODO(littlecvr): make a logo! */}
        <CardHeader
          title="Project list"
          titleTypographyProps={{
            className: classes.title,
          }}
        />
        <CardContent>
          <Divider />
          <List>
            {projectNames.length === 0 ? (
              <ListItem className={classes.center}>
                <Typography variant="subtitle1">
                  no projects, create or add an existing one
                </Typography>
              </ListItem>
            ) : (
              projectNames.map((name) => (
                <ListItem
                  key={name}
                  button
                  onClick={() => switchProject(name)}
                >
                  <ListItemText primary={name} />
                  <ListItemSecondaryAction>
                    <Tooltip title="delete this project">
                      <IconButton
                        color="inherit"
                        onClick={() => deleteProject(name)}
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Tooltip>
                  </ListItemSecondaryAction>
                </ListItem>
              ))
            )}
          </List>
          <Divider />
        </CardContent>

        <div className={classes.center}>OR</div>

        <CardContent>
          <CreateProjectForm
            projectNames={projectNames}
            onSubmit={this.handleSubmit}
          />
        </CardContent>
      </Card>
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  projects: getProjects(state),
});

const mapDispatchToProps = {
  createProject,
  deleteProject,
  fetchProjects,
  switchProject,
  resetForm: () => reset(CREATE_PROJECT_FORM),
};

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(ProjectsApp));
