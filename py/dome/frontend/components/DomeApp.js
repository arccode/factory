// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import React from 'react';

import WelcomePage from './WelcomePage';
import AppPage from './AppPage';
import TaskList from './TaskList';

var DomeApp = React.createClass({
  propTypes: {
    board: React.PropTypes.string.isRequired
  },

  setTaskListCollapsed(collapsed) {
    this.setState({taskListCollapsed: collapsed});
  },

  getInitialState() {
    return {
      taskListCollapsed: false
    };
  },

  render() {
    return (
      <div>
        {this.props.board === '' && <WelcomePage />}
        {this.props.board !== '' && <AppPage />}

        <TaskList
          collapsed={this.state.taskListCollapsed}
          setCollapsed={this.setTaskListCollapsed}
        />
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    board: state.getIn(['dome', 'currentBoard'])
  };
}

export default connect(mapStateToProps, null)(DomeApp);
