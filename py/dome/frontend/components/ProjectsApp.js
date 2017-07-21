// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import {List, ListItem} from 'material-ui/List';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import Divider from 'material-ui/Divider';
import IconButton from 'material-ui/IconButton';
import Immutable from 'immutable';
import Paper from 'material-ui/Paper';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import TextField from 'material-ui/TextField';

import DomeActions from '../actions/domeactions';

var ProjectsApp = React.createClass({
  propTypes: {
    projects: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    createProject: React.PropTypes.func.isRequired,
    deleteProject: React.PropTypes.func.isRequired,
    fetchProjects: React.PropTypes.func.isRequired,
    switchProject: React.PropTypes.func.isRequired
  },

  handleCreate() {
    // first, make sure the name field is not empty
    this.setState({nameInputErrorText: ''});
    if (this.state.nameInputValue == '') {
      this.setState({nameInputErrorText: 'This field cannot be empty'});
      return;
    }

    this.props.createProject(this.state.nameInputValue);
    this.setState({nameInputValue: ''});
  },

  handleSubmit(event) {
    event.preventDefault();  // prevent the form from submitting itself
    this.handleCreate();
  },

  getInitialState() {
    return {
      nameInputValue: '',
      nameInputErrorText: ''
    };
  },

  componentDidMount() {
    this.props.fetchProjects();
  },

  render() {
    const style = {margin: 24};
    const {projects, switchProject, deleteProject} = this.props;
    return (
      <Paper style={{
        maxWidth: 400, height: '100%',
        margin: 'auto', padding: 20,
        textAlign: 'center'
      }}>
        {/* TODO(littlecvr): make a logo! */}
        <h1 style={{textAlign: 'center'}}>Project list</h1>

        <div style={style}>
          <Divider />
          {projects.size <= 0 && <div style={{marginTop: 16, marginBottom: 16}}>
            no projects, create or add an existing one
          </div>}
          {projects.size > 0 && <List style={{textAlign: 'left'}}>
            {projects.keySeq().sort().toArray().map(name => {
              return (
                <ListItem
                  key={name}
                  primaryText={name}
                  onTouchTap={() => switchProject(name)}
                  rightIconButton={
                    <IconButton
                      tooltip="delete this project"
                      onTouchTap={() => deleteProject(name)}
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
          onSubmit={this.handleSubmit}  // called when enter key is pressed
        >
          <TextField
            name="name"
            fullWidth={true}
            floatingLabelText="New project name"
            value={this.state.nameInputValue}
            onChange={e => this.setState({nameInputValue: e.target.value})}
            errorText={this.state.nameInputErrorText}
          />
          <RaisedButton
            label="CREATE A NEW PROJECT"
            primary={true}
            fullWidth={true}
            onTouchTap={this.handleCreate}
          />
        </form>
      </Paper>
    );
  }
});

function mapStateToProps(state) {
  return {
    projects: state.getIn(['dome', 'projects'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    createProject: name => dispatch(DomeActions.createProject(name)),
    deleteProject: name => dispatch(DomeActions.deleteProject(name)),
    fetchProjects: () => dispatch(DomeActions.fetchProjects()),
    switchProject:
        nextProject => dispatch(DomeActions.switchProject(nextProject))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(ProjectsApp);
