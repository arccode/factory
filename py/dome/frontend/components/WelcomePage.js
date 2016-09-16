// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import {List, ListItem} from 'material-ui/List';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import Divider from 'material-ui/Divider';
import FlatButton from 'material-ui/FlatButton';
import IconButton from 'material-ui/IconButton';
import Immutable from 'immutable';
import Paper from 'material-ui/Paper';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import TextField from 'material-ui/TextField';

import DomeActions from '../actions/domeactions';

var WelcomePage = React.createClass({
  propTypes: {
    boards: React.PropTypes.instanceOf(Immutable.List).isRequired,

    addBoard: React.PropTypes.func.isRequired,
    createBoard: React.PropTypes.func.isRequired,
    deleteBoard: React.PropTypes.func.isRequired,

    fetchBoards: React.PropTypes.func.isRequired,
    switchBoard: React.PropTypes.func.isRequired
  },

  handleAdd() {
    var name = this.state.nameInputValue;
    var host = this.state.hostInputValue;
    var port = this.state.portInputValue;
    this.props.addBoard(name, host, port);
  },

  handleCreate() {
    var name = this.state.nameInputValue;
    var port = this.state.portInputValue;
    var factoryToolkitFile = this.fileInput.files[0];
    this.props.createBoard(name, port, factoryToolkitFile);
  },

  setShowAddBoardForm(show, event) {
    event.preventDefault();
    this.setState({showAddBoardForm: show});
  },

  getInitialState() {
    return {
      showAddBoardForm: false,
      nameInputValue: '',
      hostInputValue: 'localhost',
      portInputValue: 8080
    };
  },

  componentDidMount() {
    this.props.fetchBoards();
  },

  render() {
    const style = {margin: 24};
    const {boards, switchBoard, deleteBoard} = this.props;
    return (
      <Paper style={{
        maxWidth: 400, height: '100%',
        margin: 'auto', padding: 20,
        textAlign: 'center'
      }}>
        {/* TODO(littlecvr): make a logo! */}
        <h1 style={{textAlign: 'center'}}>Dome</h1>

        <div style={style}>
          <Divider />
          {boards.size <= 0 && <div style={{marginTop: 16, marginBottom: 16}}>
            no boards, create or add an existing one
          </div>}
          {boards.size > 0 && <List style={{textAlign: 'left'}}>
            {boards.map(board => {
              var name = board.get('name');
              return (
                <ListItem
                  key={name}
                  primaryText={name}
                  onTouchTap={() => switchBoard(board.get('name'))}
                  rightIconButton={
                    <IconButton
                      tooltip="delete this board"
                      onTouchTap={() => deleteBoard(board.get('name'))}
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

        <form style={style}>
          <TextField
            name="name"
            fullWidth={true}
            floatingLabelText="New board name"
            value={this.state.nameInputValue}
            onChange={e => this.setState({nameInputValue: e.target.value})}
          />
          {this.state.showAddBoardForm && <TextField
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
          <input type="file" className="hidden" ref={c => this.fileInput = c} />
          {!this.state.showAddBoardForm && <FlatButton
            label="SELECT THE FACTORY TOOLKIT FILE"
            primary={true}
            style={{marginBottom: 8, width: '100%'}}
            onTouchTap={() => this.fileInput.click()}
          />}
          {!this.state.showAddBoardForm && <RaisedButton
            label="CREATE A NEW BOARD"
            primary={true}
            fullWidth={true}
            // TODO(littlecvr): implement this
            onTouchTap={this.handleCreate}
          />}
          {!this.state.showAddBoardForm && <div style={style}>
            If you had manually set up the Umpire Docker container, you can
            {' '}
            <a href="#" onClick={e => this.setShowAddBoardForm(true, e)}>
              add an existing board
            </a>.
          </div>}
          {this.state.showAddBoardForm && <RaisedButton
            label="ADD AN EXISTING BOARD"
            primary={true}
            fullWidth={true}
            // TODO(littlecvr): implement this
            onTouchTap={this.handleAdd}
          />}
          {this.state.showAddBoardForm && <div style={style}>
            If you had not set up the Umpire Docker container, you should {' '}
            <a href="#" onClick={e => this.setShowAddBoardForm(false, e)}>
              create a new board
            </a>.
          </div>}
        </form>
      </Paper>
    );
  }
});

function mapStateToProps(state) {
  return {
    boards: state.getIn(['dome', 'boards'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    addBoard: (name, host, port) =>
        dispatch(DomeActions.addBoard(name, host, port)),
    createBoard: (name, port, factoryToolkitFile) =>
        dispatch(DomeActions.createBoard(name, port, factoryToolkitFile)),
    deleteBoard: board => dispatch(DomeActions.deleteBoard(board)),
    fetchBoards: () => dispatch(DomeActions.fetchBoards()),
    switchBoard: nextBoard => dispatch(DomeActions.switchBoard(nextBoard))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(WelcomePage);
