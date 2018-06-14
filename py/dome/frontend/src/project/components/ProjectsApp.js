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
import TextField from 'material-ui/TextField';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import {
  createProject,
  deleteProject,
  fetchProjects,
  switchProject,
} from '../actions';
import {getProjects} from '../selectors';

class ProjectsApp extends React.Component {
  static propTypes = {
    projects: PropTypes.instanceOf(Immutable.Map).isRequired,
    createProject: PropTypes.func.isRequired,
    deleteProject: PropTypes.func.isRequired,
    fetchProjects: PropTypes.func.isRequired,
    switchProject: PropTypes.func.isRequired,
  };

  state = {
    nameInputValue: '',
    nameInputErrorText: '',
  };

  handleCreate = () => {
    // first, make sure the name field is not empty
    this.setState({nameInputErrorText: ''});
    if (this.state.nameInputValue == '') {
      this.setState({nameInputErrorText: 'This field cannot be empty'});
      return;
    }

    this.props.createProject(this.state.nameInputValue);
    this.setState({nameInputValue: ''});
  };

  handleSubmit = (event) => {
    event.preventDefault(); // prevent the form from submitting itself
    this.handleCreate();
  };

  componentDidMount() {
    this.props.fetchProjects();
  }

  render() {
    const style = {margin: 24};
    const {projects, switchProject, deleteProject} = this.props;
    return (
      <Paper style={{
        maxWidth: 400, height: '100%',
        margin: 'auto', padding: 20,
        textAlign: 'center',
      }}>
        {/* TODO(littlecvr): make a logo! */}
        <h1 style={{textAlign: 'center'}}>Project list</h1>

        <div style={style}>
          <Divider />
          {projects.size <= 0 && <div style={{marginTop: 16, marginBottom: 16}}>
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

        <div style={style}>OR</div>

        <form
          style={style}
          onSubmit={this.handleSubmit} // called when enter key is pressed
        >
          <TextField
            name='name'
            fullWidth={true}
            floatingLabelText='New project name'
            value={this.state.nameInputValue}
            onChange={(e) => this.setState({nameInputValue: e.target.value})}
            errorText={this.state.nameInputErrorText}
          />
          <RaisedButton
            label='CREATE A NEW PROJECT'
            primary={true}
            fullWidth={true}
            onClick={this.handleCreate}
          />
        </form>
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
};

export default connect(mapStateToProps, mapDispatchToProps)(ProjectsApp);
