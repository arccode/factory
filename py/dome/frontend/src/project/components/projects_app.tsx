// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Divider from 'material-ui/Divider';
import IconButton from 'material-ui/IconButton';
import {List, ListItem} from 'material-ui/List';
import Paper from 'material-ui/Paper';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import React from 'react';
import {connect} from 'react-redux';
import {reset} from 'redux-form';

import {RootState} from '@app/types';

import {
  createProject,
  deleteProject,
  fetchProjects,
  switchProject,
} from '../actions';
import {CREATE_PROJECT_FORM} from '../constants';
import {getProjects} from '../selectors';
import {ProjectMap} from '../types';

import CreateProjectForm, {CreateProjectFormData} from './create_project_form';

interface ProjectAppProps {
  projects: ProjectMap;
  createProject: (name: string) => any;
  deleteProject: (name: string) => any;
  fetchProjects: () => any;
  switchProject: (name: string) => any;
  resetForm: () => any;
}

class ProjectsApp extends React.Component<ProjectAppProps> {
  handleSubmit = ({name}: CreateProjectFormData) => {
    this.props.createProject(name);
    this.props.resetForm();
  }

  componentDidMount() {
    this.props.fetchProjects();
  }

  render() {
    const style = {margin: 24};
    const {projects, switchProject, deleteProject} = this.props;
    const projectNames = Object.keys(projects).sort();
    return (
      <Paper
        style={{
          maxWidth: 400, height: '100%',
          margin: 'auto', padding: 20,
        }}
      >
        {/* TODO(littlecvr): make a logo! */}
        <h1 style={{textAlign: 'center'}}>Project list</h1>

        <div style={style}>
          <Divider />
          {projectNames.length === 0 ?
            (<div
              style={{textAlign: 'center', marginTop: 16, marginBottom: 16}}
            >
              no projects, create or add an existing one
            </div>) :
            (<List style={{textAlign: 'left'}}>
              {projectNames.map((name) => {
                return (
                  <ListItem
                    key={name}
                    primaryText={name}
                    onClick={() => switchProject(name)}
                    rightIconButton={
                      <IconButton
                        tooltip="delete this project"
                        onClick={() => deleteProject(name)}
                      >
                        <DeleteIcon />
                      </IconButton>
                    }
                  />
                );
              })}
            </List>)}
          <Divider />
        </div>

        <div style={{textAlign: 'center', ...style}}>OR</div>

        <div style={style}>
          <CreateProjectForm
            projectNames={projectNames}
            onSubmit={this.handleSubmit}
          />
        </div>
      </Paper>
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

export default connect(mapStateToProps, mapDispatchToProps)(ProjectsApp);
