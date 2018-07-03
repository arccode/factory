// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import Divider from 'material-ui/Divider';
import IconButton from 'material-ui/IconButton';
import {List, ListItem} from 'material-ui/List';
import Paper from 'material-ui/Paper';
import RaisedButton from 'material-ui/RaisedButton';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {formPropTypes, reset} from 'redux-form';
import {Field, reduxForm} from 'redux-form/immutable';

import {renderTextField, validateRequired} from '@common/form';

import {
  createProject,
  deleteProject,
  fetchProjects,
  switchProject,
} from '../actions';
import {CREATE_PROJECT_FORM} from '../constants';
import {getProjects} from '../selectors';

class CreateProjectForm extends React.Component {
  static propTypes = {
    projectNames: PropTypes.arrayOf(PropTypes.string).isRequired,
    ...formPropTypes,
  };

  validateUnique = (value) => {
    return this.props.projectNames.includes(value)
      ? `${value} already exist` : undefined;
  }

  render() {
    const {handleSubmit} = this.props;
    return <form onSubmit={handleSubmit}>
      <Field name='name' label='New project name'
        validate={[validateRequired, this.validateUnique]}
        component={renderTextField} />
      <RaisedButton
        label='CREATE A NEW PROJECT' primary={true} fullWidth={true}
        type='submit' />
    </form>;
  }
}

CreateProjectForm = reduxForm({
  form: CREATE_PROJECT_FORM,
})(CreateProjectForm);

class ProjectsApp extends React.Component {
  static propTypes = {
    projects: PropTypes.instanceOf(Immutable.Map).isRequired,
    createProject: PropTypes.func.isRequired,
    deleteProject: PropTypes.func.isRequired,
    fetchProjects: PropTypes.func.isRequired,
    switchProject: PropTypes.func.isRequired,
    resetForm: PropTypes.func.isRequired,
  };

  handleSubmit = (values) => {
    this.props.createProject(values.get('name'));
    this.props.resetForm();
  };

  componentDidMount() {
    this.props.fetchProjects();
  }

  render() {
    const style = {margin: 24};
    const centerStyle = {textAlign: 'center'};
    const {projects, switchProject, deleteProject} = this.props;
    return (
      <Paper style={{
        maxWidth: 400, height: '100%',
        margin: 'auto', padding: 20,
      }}>
        {/* TODO(littlecvr): make a logo! */}
        <h1 style={centerStyle}>Project list</h1>

        <div style={style}>
          <Divider />
          {projects.size <= 0 &&
              <div style={{...centerStyle, marginTop: 16, marginBottom: 16}}>
                no projects, create or add an existing one
              </div>}
          {projects.size > 0 && <List style={{textAlign: 'left'}}>
            {projects.keySeq().sort().toArray().map((name) => {
              return (
                <ListItem
                  key={name}
                  primaryText={name}
                  onClick={() => switchProject(name)}
                  rightIconButton={
                    <IconButton
                      tooltip='delete this project'
                      onClick={() => deleteProject(name)}
                    >
                      <DeleteIcon />
                    </IconButton>
                  }
                />
              );
            })}
          </List>}
          <Divider />
        </div>

        <div style={{...style, ...centerStyle}}>OR</div>

        <div style={style}>
          <CreateProjectForm projectNames={projects.keySeq().toJS()}
            onSubmit={this.handleSubmit}>
          </CreateProjectForm>
        </div>
      </Paper>
    );
  }
}

const mapStateToProps = (state) => ({
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
