// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Dialog from 'material-ui/Dialog';
import RaisedButton from 'material-ui/RaisedButton';
import TextField from 'material-ui/TextField';
import PropTypes from 'prop-types';
import React from 'react';

const _SPACE_BETWEEN_COMPONENTS = 24;

class EnablingUmpireForm extends React.Component {
  static propTypes = {
    projectName: PropTypes.string.isRequired,
    onCancel: PropTypes.func.isRequired,
    onConfirm: PropTypes.func.isRequired,
    opened: PropTypes.bool.isRequired,
  };

  state = {
    showAddForm: false,
    hostInputValue: 'localhost',
    portInputValue: 8080,
  };

  buildUmpireSettings = (addExistingOne, host, port) => {
    // TODO(littlecvr): should not need to add 'umpire_' prefix
    const settings = {
      'umpireAddExistingOne': addExistingOne,
      'umpireHost': host,
      'umpirePort': port,
    };
    return settings;
  };

  handleAdd = () => {
    this.props.onConfirm(this.props.projectName, this.buildUmpireSettings(
        true, this.state.hostInputValue, this.state.portInputValue
    ));
  };

  handleCreate = () => {
    this.props.onConfirm(this.props.projectName, this.buildUmpireSettings(
        false, 'localhost', this.state.portInputValue
    ));
  };

  setShowAddForm = (show, event) => {
    event.preventDefault();
    this.setState({showAddForm: show});
  };

  static getDerivedStateFromProps(props, state) {
    if (props.opened !== state.lastOpened) {
      const ret = {lastOpened: props.opened};
      if (props.opened) {
        Object.assign(ret, {
          hostInputValue: 'localhost',
          portInputValue: 8080,
        });
      }
      return ret;
    }
    return null;
  }

  componentDidUpdate(prevProps, prevState) {
    if (this.props.opened && !prevProps.opened) {
      this.formElement.reset();
    }
  }

  render() {
    return (
      <form ref={(c) => this.formElement = c}>
        <Dialog
          title='Enable Umpire'
          open={this.props.opened}
          modal={false}
          onRequestClose={this.props.onCancel}
          actions={<div>
            {!this.state.showAddForm && <RaisedButton
              label='CREATE A NEW UMPIRE INSTANCE'
              primary={true}
              onClick={this.handleCreate}
              style={{marginLeft: _SPACE_BETWEEN_COMPONENTS}}
            />}
            {this.state.showAddForm && <RaisedButton
              label='ADD AN EXISTING UMPIRE INSTANCE'
              primary={true}
              onClick={this.handleAdd}
              style={{marginLeft: _SPACE_BETWEEN_COMPONENTS}}
            />}
            <RaisedButton
              label='CANCEL'
              primary={true}
              onClick={this.props.onCancel}
              style={{marginLeft: _SPACE_BETWEEN_COMPONENTS}}
            />
          </div>}
        >
          {this.state.showAddForm && <TextField
            name='host'
            fullWidth={true}
            floatingLabelText='host'
            value={this.state.hostInputValue}
            onChange={(e) => this.setState({hostInputValue: e.target.value})}
          />}
          <TextField
            name='port'
            fullWidth={true}
            floatingLabelText='Port'
            value={this.state.portInputValue}
            onChange={(e) => this.setState({portInputValue: e.target.value})}
          />
          <div style={{
            textAlign: 'center', marginTop: _SPACE_BETWEEN_COMPONENTS,
          }}>
            {!this.state.showAddForm && <div>
              If you had manually set up the Umpire Docker container, you can
              {' '}
              <a href='#' onClick={(e) => this.setShowAddForm(true, e)}>
                add the existing one
              </a>.
            </div>}
            {this.state.showAddForm && <div>
              If you had not set up the Umpire Docker container, you should
              {' '}
              <a href='#' onClick={(e) => this.setShowAddForm(false, e)}>
                create a new one
              </a>.
            </div>}
          </div>
        </Dialog>
      </form>
    );
  }
}

export default EnablingUmpireForm;
