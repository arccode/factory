// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Grid from '@material-ui/core/Grid';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import classNames from 'classnames';
import React from 'react';
import {hot} from 'react-hot-loader';
import Measure from 'react-measure';
import {connect} from 'react-redux';

import auth from '@app/auth';
import LoginApp from '@app/auth/components/login_app';
import BundlesApp from '@app/bundle/components/bundles_app';
import ConfigApp from '@app/config/components/config_app';
import DashboardApp from '@app/dashboard/components/dashboard_app';
import ErrorDialog from '@app/error/components/error_dialog';
import ProjectsApp from '@app/project/components/projects_app';
import TaskList from '@app/task/components/task_list';
import {RootState} from '@app/types';

import {fetchDomeInfo} from '../actions';
import {getCurrentApp} from '../selectors';
import {AppName} from '../types';

import DomeAppBar from './dome_app_bar';
import DomeAppMenu from './dome_app_menu';

const APP_MENU_WIDTH = 250;
const SPACE_BEFORE_TASK_LIST = 24;
const SPACE_AFTER_TASK_LIST = 24;

const style = (theme: Theme) => createStyles({
  root: {
    fontSize: theme.typography.fontSize,
    fontFamily: theme.typography.fontFamily,
  },
  // This is same as material-ui Drawer's transition.
  app: {
    transition: theme.transitions.create('margin', {
      easing: theme.transitions.easing.sharp,
      duration: theme.transitions.duration.leavingScreen,
    }),
    padding: theme.spacing.unit * 2,
  },
  appShift: {
    marginLeft: APP_MENU_WIDTH,
    transition: theme.transitions.create('margin', {
      easing: theme.transitions.easing.easeOut,
      duration: theme.transitions.duration.enteringScreen,
    }),
  },
});

interface DomeAppProps extends WithStyles<typeof style> {
  isLoggedIn: boolean;
  appName: AppName;
  testAuthToken: () => any;
  fetchDomeInfo: () => any;
}

interface DomeAppState {
  appMenuOpened: boolean;
  taskListHeight: number;
}

class DomeApp extends React.Component<DomeAppProps, DomeAppState> {
  state = {
    appMenuOpened: true,
    taskListHeight: 0,
  };

  toggleAppMenu = () => {
    this.setState({appMenuOpened: !this.state.appMenuOpened});
  }

  componentDidMount() {
    // check if user's using Chrome/Chromium
    if (!navigator.userAgent.includes('Chrome')) {
      window.alert(`Warning!!
To visit Dome, please use Chrome/Chromium to avoid unnecessary issues.`);
    }
    this.props.testAuthToken();
    this.props.fetchDomeInfo();
  }

  render() {
    const {isLoggedIn, appName, classes} = this.props;
    const {appMenuOpened} = this.state;

    // must not let the task list cover the main content
    const marginBottom = SPACE_BEFORE_TASK_LIST +
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
      app = <BundlesApp offset={marginBottom} />;
    } else {
      console.error(`Unknown app ${appName}`);
    }

    return (
      <div className={classes.root}>
        <DomeAppBar toggleAppMenu={this.toggleAppMenu} />
        <DomeAppMenu open={appMenuOpened} width={APP_MENU_WIDTH} />

        <div
          className={classNames(classes.app, appMenuOpened && classes.appShift)}
        >
          <Grid container justify="center">
            <Grid item xs={12} sm={9} md={6}>
              {app}
            </Grid>
          </Grid>
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
});

const mapDispatchToProps = {
  testAuthToken: auth.actions.testAuthToken,
  fetchDomeInfo,
};

export default hot(module)(
  connect(mapStateToProps, mapDispatchToProps)(withStyles(style)(DomeApp)));
