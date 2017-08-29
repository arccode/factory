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
import LoginApp from './LoginApp';
import ProjectsApp from './ProjectsApp';
import BundlesApp from './BundlesApp';
import ConfigApp from './ConfigApp';
import DashboardApp from './DashboardApp';
import DomeActions from '../actions/domeactions';
import ErrorDialog from './ErrorDialog';
import FixedAppBar from './FixedAppBar';
import TaskList from './TaskList';

const _APP_MENU_WIDTH = 250;
const _PROJECT_MENU_ITEM_PADDING_LEFT = 36;
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
    isLoggedIn: React.PropTypes.bool.isRequired,
    appName: React.PropTypes.string.isRequired,
    project: React.PropTypes.instanceOf(Immutable.Map).isRequired,
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
    const {isLoggedIn, appName, project} = this.props;

    // must not let the task list cover the main content
    var paddingBottom = _SPACE_BEFORE_TASK_LIST +
        this.state.taskListHeight + _SPACE_AFTER_TASK_LIST;

    // TODO(b/31579770): should define a "app" system (like a dynamic module
    //                   system), which automatically import and display
    //                   corresponding app intead of writing a long if-elif-else
    //                   statement.
    var app = null;
    if (!isLoggedIn) {
      app = <LoginApp />;
    } else if (appName == AppNames.PROJECTS_APP) {
      app = <ProjectsApp />;
    } else if (appName == AppNames.CONFIG_APP) {
      app = <ConfigApp />;
    } else if (appName == AppNames.DASHBOARD_APP) {
      app = <DashboardApp />;
    } else if (appName == AppNames.BUNDLES_APP) {
      // TODO(littlecvr): standardize the floating button API so we don't need
      //                  to pass offset like this
      app = <BundlesApp offset={paddingBottom} />;
    } else {
      console.error(`Unknown app ${appName}`);
    }

    const projectName = project.get('name', '');

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
          {isLoggedIn && <div>
            {projectName != '' && <Subheader>{projectName}</Subheader>}
            {projectName != '' &&
              <MenuItem
                onTouchTap={() => this.handleClick(AppNames.DASHBOARD_APP)}
                innerDivStyle={{paddingLeft: _PROJECT_MENU_ITEM_PADDING_LEFT}}
              >
                Dashboard
              </MenuItem>
            }
            {projectName != '' && project.get('umpireEnabled') &&
              <MenuItem
                onTouchTap={() => this.handleClick(AppNames.BUNDLES_APP)}
                innerDivStyle={{paddingLeft: _PROJECT_MENU_ITEM_PADDING_LEFT}}
                disabled={!project.get('umpireReady')}
              >
                Bundles{!project.get('umpireReady') && ' (activating...)'}
              </MenuItem>
            }

            {projectName != '' && <Divider />}

            <MenuItem
              onTouchTap={() => this.handleClick(AppNames.PROJECTS_APP)}>
              Change project
            </MenuItem>
            <Divider />
            <MenuItem
              onTouchTap={() => this.handleClick(AppNames.CONFIG_APP)}
            >
              Config
            </MenuItem>
          </div>}
        </Drawer>

        <div
          style={{paddingLeft: this.state.appMenuOpened ? _APP_MENU_WIDTH : 0}}
        >
          {app}
        </div>
        <ErrorDialog />
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
    isLoggedIn: state.getIn(['dome', 'isLoggedIn']),
    appName: state.getIn(['dome', 'currentApp']),
    project: state.getIn(
        ['dome', 'projects', state.getIn(['dome', 'currentProject'])],
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
