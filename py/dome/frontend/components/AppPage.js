// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import Drawer from 'material-ui/Drawer';
import Immutable from 'immutable';
import MenuItem from 'material-ui/MenuItem';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';

import AppNames from '../constants/AppNames';
import BundlesApp from './BundlesApp';
import DomeActions from '../actions/domeactions';
import FixedAppBar from './FixedAppBar';
import SettingsApp from './SettingsApp';
import Task from './Task';

const AppPage = React.createClass({
  propTypes: {
    dismissTask: React.PropTypes.func.isRequired,
    tasks: React.PropTypes.instanceOf(Immutable.Map).isRequired
  },

  toggleAppMenu() {
    this.setState({appMenuOpened: !this.state.appMenuOpened});
  },

  handleClick(nextApp) {
    // close the drawer
    this.setState({appMenuOpened: false});
    this.props.switchApp(nextApp);
  },

  getInitialState() {
    return {
      appMenuOpened: false
    };
  },

  render() {
    var app = null;
    if (this.props.app == AppNames.BUNDLES_APP) {
      // TODO(littlecvr): there should be a better way than passing an offset
      //                  into the app
      app = <BundlesApp offset={50 * this.props.tasks.size + 24} />;
    } else if (this.props.app == AppNames.SETTINGS_APP) {
      app = <SettingsApp />;
    } else {
      console.log(`Unknown app ${this.props.app}`);
    }

    return (
      <div>
        <FixedAppBar
          title="Dome"
          onLeftIconButtonTouchTap={this.toggleAppMenu}
        />
        <Drawer
          docked={false}
          open={this.state.appMenuOpened}
          onRequestChange={open => this.setState({appMenuOpened: open})}
        >
          <MenuItem onTouchTap={() => this.handleClick(AppNames.BUNDLES_APP)}>
            Bundles
          </MenuItem>
          <MenuItem onTouchTap={() => this.handleClick(AppNames.SETTINGS_APP)}>
            Settings
          </MenuItem>
        </Drawer>
        {app}

        {this.props.tasks.keySeq().toArray().map((taskID, index) => {
          var task = this.props.tasks.get(taskID);
          return (
            <Task
              key={taskID}
              state={task.get('state')}
              description={task.get('description')}
              style={{
                position: 'fixed',
                padding: 5,
                right: 24,
                bottom: 50 * index + 24  // stack them
              }}
              cancel={() => console.log('not implemented')}
              dismiss={() => this.props.dismissTask(taskID)}
              retry={() => alert('not implemented yet')}
            />
          );
        })}
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    app: state.getIn(['dome', 'currentApp']),
    tasks: state.getIn(['dome', 'tasks'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    switchApp: nextApp => dispatch(DomeActions.switchApp(nextApp)),
    dismissTask: taskID => dispatch(DomeActions.dismissTask(taskID))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(AppPage);
