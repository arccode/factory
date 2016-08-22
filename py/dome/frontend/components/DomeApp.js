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
import DomeActions from '../actions/dome';
import FixedAppBar from './FixedAppBar';
import SettingsApp from './SettingsApp';

const DomeApp = React.createClass({
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
    var currentApp = null;
    if (this.props.currentApp == AppNames.BUNDLES_APP) {
        currentApp = <BundlesApp />;
    } else if (this.props.currentApp == AppNames.SETTINGS_APP) {
        currentApp = <SettingsApp />;
    } else {
      console.log(`Unknown app ${this.props.currentApp}`);
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
        {currentApp}
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    currentApp: state.getIn(['dome', 'currentApp'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    switchApp: nextApp => dispatch(DomeActions.switchApp(nextApp))
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(DomeApp);
