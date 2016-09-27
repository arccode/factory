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

var BoardsApp = React.createClass({
  propTypes: {
    boards: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    createBoard: React.PropTypes.func.isRequired,
    deleteBoard: React.PropTypes.func.isRequired,
    fetchBoards: React.PropTypes.func.isRequired,
    switchBoard: React.PropTypes.func.isRequired
  },

  handleCreate() {
    this.props.createBoard(this.state.nameInputValue);
  },

  getInitialState() {
    return {
      nameInputValue: ''
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
            {boards.keySeq().sort().toArray().map(name => {
              return (
                <ListItem
                  key={name}
                  primaryText={name}
                  onTouchTap={() => switchBoard(name)}
                  rightIconButton={
                    <IconButton
                      tooltip="delete this board"
                      onTouchTap={() => deleteBoard(name)}
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
          <RaisedButton
            label="CREATE A NEW BOARD"
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
    boards: state.getIn(['dome', 'boards'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    createBoard: name => dispatch(DomeActions.createBoard(name)),
    deleteBoard: name => dispatch(DomeActions.deleteBoard(name)),
    fetchBoards: () => dispatch(DomeActions.fetchBoards()),
    switchBoard: nextBoard => dispatch(DomeActions.switchBoard(nextBoard))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(BoardsApp);
