// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Divider from 'material-ui/Divider';
import Drawer from 'material-ui/Drawer';
import MenuItem from 'material-ui/MenuItem';
import {amber300} from 'material-ui/styles/colors';
import Subheader from 'material-ui/Subheader';
import React from 'react';
import Measure from 'react-measure';
import {connect} from 'react-redux';

import auth from '@app/auth';
import LoginApp from '@app/auth/components/LoginApp';
import BundlesApp from '@app/bundle/components/BundlesApp';
import ConfigApp from '@app/config/components/ConfigApp';
import DashboardApp from '@app/dashboard/components/DashboardApp';
import ErrorDialog from '@app/error/components/ErrorDialog';
import project from '@app/project';
import ProjectsApp from '@app/project/components/ProjectsApp';
import {Project} from '@app/project/types';
import TaskList from '@app/task/components/TaskList';
import {RootState} from '@app/types';

import {switchApp} from '../actions';
import {getCurrentApp} from '../selectors';
import {AppName} from '../types';

import FixedAppBar from './FixedAppBar';

const APP_MENU_WIDTH = 250;
const PROJECT_MENU_ITEM_PADDING_LEFT = 36;
const SPACE_BEFORE_TASK_LIST = 24;
const SPACE_AFTER_TASK_LIST = 24;

const EmphasizedString: React.SFC = ({children}) => (
  <span style={{fontWeight: 'bold', color: amber300}}>{children}</span>
);

const DomeAppBarTitle: React.SFC = () => (
  <span>
    <EmphasizedString>D</EmphasizedString>ome:
    fact<EmphasizedString>o</EmphasizedString>ry
    server <EmphasizedString>m</EmphasizedString>anagement
    consol<EmphasizedString>e</EmphasizedString>
  </span>
);

interface DomeAppProps {
  isLoggedIn: boolean;
  appName: AppName;
  project: Project;
  testAuthToken: () => any;
  switchApp: (app: AppName) => any;
}

interface DomeAppState {
  appBarHeight: number;
  appMenuOpened: boolean;
  taskListHeight: number;
}

class DomeApp extends React.Component<DomeAppProps, DomeAppState> {
  state = {
    appBarHeight: 0,
    appMenuOpened: true,
    taskListHeight: 0,
  };

  handleClick = (nextApp: AppName) => {
    // close the drawer
    this.props.switchApp(nextApp);
  }

  toggleAppMenu = () => {
    this.setState({appMenuOpened: !this.state.appMenuOpened});
  }

  componentDidMount() {
    this.props.testAuthToken();
  }

  render() {
    const {isLoggedIn, appName, project} = this.props;

    // must not let the task list cover the main content
    const paddingBottom = SPACE_BEFORE_TASK_LIST +
        this.state.taskListHeight + SPACE_AFTER_TASK_LIST;

    // TODO(b/31579770): should define a "app" system (like a dynamic module
    //                   system), which automatically import and display
    //                   corresponding app intead of writing a long if-elif-else
    //                   statement.
    let app = null;
    if (!isLoggedIn) {
      app = <LoginApp />;
    } else if (appName === 'PROJECTS_APP') {
      app = <ProjectsApp />;
    } else if (appName === 'CONFIG_APP') {
      app = <ConfigApp />;
    } else if (appName === 'DASHBOARD_APP') {
      app = <DashboardApp />;
    } else if (appName === 'BUNDLES_APP') {
      // TODO(littlecvr): standardize the floating button API so we don't need
      //                  to pass offset like this
      app = <BundlesApp offset={paddingBottom} />;
    } else {
      console.error(`Unknown app ${appName}`);
    }

    const projectName = project.name || '';

    return (
      <div style={{paddingBottom}}>
        <FixedAppBar
          title={<DomeAppBarTitle />}
          onLeftIconButtonClick={this.toggleAppMenu}
          onHeightChange={(h) => this.setState({appBarHeight: h})}
          zDepth={2} // above the drawer
        />

        <Drawer
          docked={true}
          width={APP_MENU_WIDTH}
          open={this.state.appMenuOpened}
          // Need to set "top" to avoid covering (or being covered by) the
          // AppBar, see https://github.com/callemall/material-ui/issues/957.
          // Setting zIndex is also needed because zDepth does not actually
          // affect zIndex, and not setting it would make this drawer covers the
          // shadow of AppBar.
          containerStyle={{top: this.state.appBarHeight, zIndex: 1000}}
          zDepth={1} // below the AppBar
        >
          {isLoggedIn && <div>
            {projectName !== '' && <Subheader>{projectName}</Subheader>}
            {projectName !== '' &&
              <MenuItem
                onClick={() => this.handleClick('DASHBOARD_APP')}
                innerDivStyle={{paddingLeft: PROJECT_MENU_ITEM_PADDING_LEFT}}
              >
                Dashboard
              </MenuItem>
            }
            {projectName !== '' &&
              <MenuItem
                onClick={() => this.handleClick('BUNDLES_APP')}
                innerDivStyle={{paddingLeft: PROJECT_MENU_ITEM_PADDING_LEFT}}
                disabled={!project.umpireReady}
              >
                Bundles {project.umpireEnabled &&
                    !project.umpireReady && '(activating...)'}
              </MenuItem>
            }

            {projectName !== '' && <Divider />}

            <MenuItem onClick={() => this.handleClick('PROJECTS_APP')}>
              Change project
            </MenuItem>
            <Divider />
            <MenuItem onClick={() => this.handleClick('CONFIG_APP')}>
              Config
            </MenuItem>
          </div>}
        </Drawer>

        <div
          style={{paddingLeft: this.state.appMenuOpened ? APP_MENU_WIDTH : 0}}
        >
          {app}
        </div>
        <ErrorDialog />
        <Measure onMeasure={(d) => this.setState({taskListHeight: d.height})}>
          <TaskList />
        </Measure>
      </div>
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  isLoggedIn: auth.selectors.isLoggedIn(state),
  appName: getCurrentApp(state),
  project: project.selectors.getCurrentProjectObject(state),
});

const mapDispatchToProps = {
  switchApp,
  testAuthToken: auth.actions.testAuthToken,
};

export default connect(mapStateToProps, mapDispatchToProps)(DomeApp);
