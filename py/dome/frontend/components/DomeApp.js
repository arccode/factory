// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import Drawer from 'material-ui/Drawer';
import Immutable from 'immutable';
import MenuItem from 'material-ui/MenuItem';
import React from 'react';

import AppNames from '../constants/AppNames';
import BoardsApp from './BoardsApp';
import BundlesApp from './BundlesApp';
import DomeActions from '../actions/domeactions';
import FixedAppBar from './FixedAppBar';
import SettingsApp from './SettingsApp';
import TaskList from './TaskList';

var DomeApp = React.createClass({
  propTypes: {
    app: React.PropTypes.string.isRequired,
    board: React.PropTypes.string.isRequired,
    switchApp: React.PropTypes.func.isRequired,
    tasks: React.PropTypes.instanceOf(Immutable.Map).isRequired
  },

  handleClick(nextApp) {
    // close the drawer
    this.setState({appMenuOpened: false});
    this.props.switchApp(nextApp);
  },

  setTaskListCollapsed(collapsed) {
    this.setState({taskListCollapsed: collapsed});
  },

  toggleAppMenu() {
    this.setState({appMenuOpened: !this.state.appMenuOpened});
  },

  getInitialState() {
    return {
      appMenuOpened: false,
      taskListCollapsed: false
    };
  },

  render() {
    // must not let the task list cover the main content
    // 82 = 24 + 58
    //   24: space above the task list
    //   58: height of the title bar of the task list
    // 48: height of each task item
    // 24: space below task list
    // TODO(littlecvr): find a better way to get the dimension of TaskList
    //                  instead of calculating our own
    var paddingBottom = (this.props.tasks.size == 0 ? 0 : 82) +
        48 * (this.state.taskListCollapsed ? 0 : this.props.tasks.size) + 24;

    // TODO(b/31579770): should define a "app" system (like a dynamic module
    //                   system), which automatically import and display
    //                   corresponding app intead of writing a long if-elif-else
    //                   statement.
    var app = null;
    if (this.props.app == AppNames.BOARDS_APP) {
      app = <BoardsApp />;
    } else if (this.props.app == AppNames.BUNDLES_APP) {
      // TODO(littlecvr): standardize the floating button API so we don't need
      //                  to pass offset like this
      app = <BundlesApp offset={paddingBottom} />;
    } else if (this.props.app == AppNames.SETTINGS_APP) {
      app = <SettingsApp />;
    } else {
      console.error(`Unknown app ${this.props.app}`);
    }

    return (
      <div style={{paddingBottom}}>
        <FixedAppBar
          title="Dome"
          onLeftIconButtonTouchTap={this.toggleAppMenu}
        />
        <Drawer
          docked={false}
          open={this.state.appMenuOpened}
          onRequestChange={open => this.setState({appMenuOpened: open})}
        >
          <MenuItem onTouchTap={() => this.handleClick(AppNames.BOARDS_APP)}>
            Boards
          </MenuItem>
          {/* TODO(b/31579770): leave this to the app itself to determine where
                                and when to show
          */}
          {this.props.board != '' &&
            <MenuItem onTouchTap={() => this.handleClick(AppNames.BUNDLES_APP)}>
              Bundles
            </MenuItem>
          }
          <MenuItem onTouchTap={() => this.handleClick(AppNames.SETTINGS_APP)}>
            Settings
          </MenuItem>
        </Drawer>
        {app}
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
    app: state.getIn(['dome', 'currentApp']),
    board: state.getIn(['dome', 'currentBoard']),
    tasks: state.getIn(['dome', 'tasks'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    switchApp: nextApp => dispatch(DomeActions.switchApp(nextApp))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(DomeApp);
