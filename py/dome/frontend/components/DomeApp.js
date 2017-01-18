// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {amber300} from 'material-ui/styles/colors';
import {connect} from 'react-redux';
import Divider from 'material-ui/Divider';
import Drawer from 'material-ui/Drawer';
import Immutable from 'immutable';
import Measure from 'react-measure';
import MenuItem from 'material-ui/MenuItem';
import React from 'react';
import Subheader from 'material-ui/Subheader';

import AppNames from '../constants/AppNames';
import BoardsApp from './BoardsApp';
import BundlesApp from './BundlesApp';
import DashboardApp from './DashboardApp';
import DomeActions from '../actions/domeactions';
import FixedAppBar from './FixedAppBar';
import SettingsApp from './SettingsApp';
import TaskList from './TaskList';

const _APP_MENU_WIDTH = 250;
const _BOARD_MENU_ITEM_PADDING_LEFT = 36;
const _SPACE_BEFORE_TASK_LIST = 24;
const _SPACE_AFTER_TASK_LIST = 24;

const EmphasizedString = props => (
  <span style={{fontWeight: 'bold', color: amber300}}>{props.children}</span>
);

const DomeAppBarTitle = () => (
  <span>
    <EmphasizedString>D</EmphasizedString>ome:
    fact<EmphasizedString>o</EmphasizedString>ry
    server <EmphasizedString>m</EmphasizedString>anagement
    consol<EmphasizedString>e</EmphasizedString>
  </span>
);

var DomeApp = React.createClass({
  propTypes: {
    appName: React.PropTypes.string.isRequired,
    board: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    switchApp: React.PropTypes.func.isRequired
  },

  handleClick(nextApp) {
    // close the drawer
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
      appBarHeight: 0,
      appMenuOpened: true,
      taskListCollapsed: false,
      taskListHeight: 0
    };
  },

  render() {
    const {appName, board} = this.props;

    // must not let the task list cover the main content
    var paddingBottom = _SPACE_BEFORE_TASK_LIST +
        this.state.taskListHeight + _SPACE_AFTER_TASK_LIST;

    // TODO(b/31579770): should define a "app" system (like a dynamic module
    //                   system), which automatically import and display
    //                   corresponding app intead of writing a long if-elif-else
    //                   statement.
    var app = null;
    if (appName == AppNames.BOARDS_APP) {
      app = <BoardsApp />;
    } else if (appName == AppNames.DASHBOARD_APP) {
      app = <DashboardApp />;
    } else if (appName == AppNames.BUNDLES_APP) {
      // TODO(littlecvr): standardize the floating button API so we don't need
      //                  to pass offset like this
      app = <BundlesApp offset={paddingBottom} />;
    } else if (appName == AppNames.SETTINGS_APP) {
      app = <SettingsApp />;
    } else {
      console.error(`Unknown app ${appName}`);
    }

    const boardName = board.get('name', '');

    return (
      <div style={{paddingBottom}}>
        <FixedAppBar
          title={<DomeAppBarTitle />}
          onLeftIconButtonTouchTap={this.toggleAppMenu}
          onHeightChange={h => this.setState({appBarHeight: h})}
          zDepth={2}  // above the drawer
        />
        <Drawer
          docked={true}
          width={_APP_MENU_WIDTH}
          open={this.state.appMenuOpened}
          // Need to set "top" to avoid covering (or being covered by) the
          // AppBar, see https://github.com/callemall/material-ui/issues/957.
          // Setting zIndex is also needed because zDepth does not actually
          // affect zIndex, and not setting it would make this drawer covers the
          // shadow of AppBar.
          containerStyle={{top: this.state.appBarHeight, zIndex: 1000}}
          zDepth={1}  // below the AppBar
        >
          {boardName != '' && <Subheader>{boardName}</Subheader>}
          {boardName != '' &&
            <MenuItem
              onTouchTap={() => this.handleClick(AppNames.DASHBOARD_APP)}
              innerDivStyle={{paddingLeft: _BOARD_MENU_ITEM_PADDING_LEFT}}
            >
              Dashboard
            </MenuItem>
          }
          {boardName != '' && board.get('umpireEnabled') &&
            <MenuItem
              onTouchTap={() => this.handleClick(AppNames.BUNDLES_APP)}
              innerDivStyle={{paddingLeft: _BOARD_MENU_ITEM_PADDING_LEFT}}
              disabled={!board.get('umpireReady')}
            >
              Bundles{!board.get('umpireReady') && ' (activating...)'}
            </MenuItem>
          }
          {boardName != '' &&
            <MenuItem
              onTouchTap={() => console.warn('not implemented yet')}
              innerDivStyle={{paddingLeft: _BOARD_MENU_ITEM_PADDING_LEFT}}
            >
              DRM keys
            </MenuItem>
          }
          {boardName != '' &&
            <MenuItem
              onTouchTap={() => console.warn('not implemented yet')}
              innerDivStyle={{paddingLeft: _BOARD_MENU_ITEM_PADDING_LEFT}}
            >
              Logs
            </MenuItem>
          }

          {boardName != '' && <Divider />}

          <MenuItem onTouchTap={() => this.handleClick(AppNames.BOARDS_APP)}>
            Change board
          </MenuItem>
          <MenuItem onTouchTap={() => this.handleClick(AppNames.SETTINGS_APP)}>
            Settings
          </MenuItem>
        </Drawer>
        <div
          style={{paddingLeft: this.state.appMenuOpened ? _APP_MENU_WIDTH : 0}}
        >
          {app}
        </div>
        <Measure onMeasure={d => this.setState({taskListHeight: d.height})}>
          <TaskList
            collapsed={this.state.taskListCollapsed}
            setCollapsed={this.setTaskListCollapsed}
          />
        </Measure>
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    appName: state.getIn(['dome', 'currentApp']),
    board: state.getIn(
        ['dome', 'boards', state.getIn(['dome', 'currentBoard'])],
        Immutable.Map()
    )
  };
}

function mapDispatchToProps(dispatch) {
  return {
    switchApp: nextApp => dispatch(DomeActions.switchApp(nextApp))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(DomeApp);
