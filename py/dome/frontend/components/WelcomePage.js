// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import MenuItem from 'material-ui/MenuItem';
import Paper from 'material-ui/Paper';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import SelectField from 'material-ui/SelectField';
import TextField from 'material-ui/TextField';

import DomeActions from '../actions/domeactions';

var WelcomePage = React.createClass({
  propTypes: {
    boards: React.PropTypes.string.isRequired,
    fetchBoards: React.PropTypes.func.isRequired,
    switchBoard: React.PropTypes.func.isRequired
  },

  handleSelectChange(event, index, value) {
    if (value === '') {
      return;
    }
    this.props.switchBoard(value);
  },

  setShowAddBoardForm(show, event) {
    event.preventDefault();
    this.setState({showAddBoardForm: show});
  },

  getInitialState() {
    return {
      showAddBoardForm: false
    };
  },

  componentDidMount() {
    this.props.fetchBoards();
  },

  render: function() {
    const style = {margin: 24};
    return (
      <Paper style={{
        maxWidth: 400, height: '100%',
        margin: 'auto', padding: 20,
        textAlign: 'center'
      }}>
        {/* TODO(littlecvr): make a logo! */}
        <h1 style={{textAlign: 'center'}}>Dome</h1>

        <div style={style}>
          <SelectField
            style={{textAlign: 'initial'}}
            fullWidth={true}
            floatingLabelText="SELECT A BOARD"
            onChange={this.handleSelectChange}
          >
            {this.props.boards.map(board => {
              var name = board.get('name');
              return <MenuItem key={name} value={name} primaryText={name} />;
            })}
          </SelectField>
        </div>

        <div style={style}>OR</div>

        <form style={style}>
          <TextField
            name="name"
            fullWidth={true}
            floatingLabelText="New board name"
          />
          {!this.state.showAddBoardForm && <RaisedButton
            label="CREATE A NEW BOARD"
            primary={true}
            fullWidth={true}
            // TODO(littlecvr): implement this
            onTouchTap={() => alert('not implemented yet')}
          />}
          {!this.state.showAddBoardForm && <div style={style}>
            If you had manually set up the Umpire Docker container, you can
            {' '}
            <a href="#" onClick={e => this.setShowAddBoardForm(true, e)}>
              add an existing board
            </a>.
          </div>}
          {this.state.showAddBoardForm && <TextField
            name="url"
            fullWidth={true}
            floatingLabelText="URL to Umpire RPC server"
            hintText="http://localhost:8080/"
          />}
          {this.state.showAddBoardForm && <RaisedButton
            label="ADD AN EXISTING BOARD"
            primary={true}
            fullWidth={true}
            // TODO(littlecvr): implement this
            onTouchTap={() => alert('not implemented yet')}
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
    fetchBoards: () => dispatch(DomeActions.fetchBoards()),
    switchBoard: nextBoard => dispatch(DomeActions.switchBoard(nextBoard))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(WelcomePage);
