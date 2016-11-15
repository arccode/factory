// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import TextField from 'material-ui/TextField';

var _SPACE_BETWEEN_COMPONENTS = 24;

var EnablingUmpireForm = React.createClass({
  propTypes: {
    boardName: React.PropTypes.string.isRequired,
    onCancel: React.PropTypes.func.isRequired,
    onConfirm: React.PropTypes.func.isRequired,
    opened: React.PropTypes.bool.isRequired
  },

  buildUmpireSettings(addExistingOne, host, port) {
    // TODO(littlecvr): should not need to add 'umpire_' prefix
    let settings = {
      'umpireAddExistingOne': addExistingOne,
      'umpireHost': host,
      'umpirePort': port
    };
    return settings;
  },

  handleAdd() {
    this.props.onConfirm(this.props.boardName, this.buildUmpireSettings(
        true, this.state.hostInputValue, this.state.portInputValue
    ));
  },

  handleCreate() {
    this.props.onConfirm(this.props.boardName, this.buildUmpireSettings(
        false, 'localhost', this.state.portInputValue
    ));
  },

  setShowAddForm(show, event) {
    event.preventDefault();
    this.setState({showAddForm: show});
  },

  getInitialState() {
    return {
      showAddForm: false,
      hostInputValue: 'localhost',
      portInputValue: 8080
    };
  },

  componentWillReceiveProps(nextProps) {
    // reset every time the form has just been opened
    if (nextProps.opened && !this.props.opened) {
      this.formElement.reset();
      this.setState({
        hostInputValue: 'localhost',
        portInputValue: 8080
      });
    }
  },

  render() {
    return (
      <form ref={c => this.formElement = c}>
        <Dialog
          title="Enable Umpire"
          open={this.props.opened}
          modal={false}
          onRequestClose={this.props.onCancel}
          actions={<div>
            {!this.state.showAddForm && <RaisedButton
              label="CREATE A NEW UMPIRE INSTANCE"
              primary={true}
              onTouchTap={this.handleCreate}
              style={{marginLeft: _SPACE_BETWEEN_COMPONENTS}}
            />}
            {this.state.showAddForm && <RaisedButton
              label="ADD AN EXISTING UMPIRE INSTANCE"
              primary={true}
              onTouchTap={this.handleAdd}
              style={{marginLeft: _SPACE_BETWEEN_COMPONENTS}}
            />}
            <RaisedButton
              label="CANCEL"
              primary={true}
              onTouchTap={this.props.onCancel}
              style={{marginLeft: _SPACE_BETWEEN_COMPONENTS}}
            />
          </div>}
        >
          {this.state.showAddForm && <TextField
            name="host"
            fullWidth={true}
            floatingLabelText="host"
            value={this.state.hostInputValue}
            onChange={e => this.setState({hostInputValue: e.target.value})}
          />}
          <TextField
            name="port"
            fullWidth={true}
            floatingLabelText="Port"
            value={this.state.portInputValue}
            onChange={e => this.setState({portInputValue: e.target.value})}
          />
          <div style={{
            textAlign: 'center', marginTop: _SPACE_BETWEEN_COMPONENTS
          }}>
            {!this.state.showAddForm && <div>
              If you had manually set up the Umpire Docker container, you can
              {' '}
              <a href="#" onClick={e => this.setShowAddForm(true, e)}>
                add the existing one
              </a>.
            </div>}
            {this.state.showAddForm && <div>
              If you had not set up the Umpire Docker container, you should
              {' '}
              <a href="#" onClick={e => this.setShowAddForm(false, e)}>
                create a new one
              </a>.
            </div>}
          </div>
        </Dialog>
      </form>
    );
  }
});

export default EnablingUmpireForm;
