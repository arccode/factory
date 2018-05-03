// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardTitle, CardText} from 'material-ui/Card';
import {connect} from 'react-redux';
import React from 'react';
import Toggle from 'material-ui/Toggle';
import RaisedButton from 'material-ui/RaisedButton';

import DomeActions from '../actions/domeactions';

var ConfigApp = React.createClass({
  propTypes: {
    TFTPEnabled: React.PropTypes.bool.isRequired,
    configUpdating: React.PropTypes.bool.isRequired,
    disableTFTP: React.PropTypes.func.isRequired,
    enableTFTP: React.PropTypes.func.isRequired,
    initializeConfig: React.PropTypes.func.isRequired,
    logout: React.PropTypes.func.isRequired
  },

  componentDidMount() {
    this.props.initializeConfig();
  },

  render() {
    const {
      TFTPEnabled,
      configUpdating,
      disableTFTP,
      enableTFTP,
      logout
    } = this.props;

    return (
      <div>
        <Card>
          <CardTitle title={'Config'}></CardTitle>
          <CardText>
            <Toggle
              label='TFTP server'
              toggled={TFTPEnabled}
              onToggle={TFTPEnabled ? disableTFTP : enableTFTP}
              disabled={configUpdating}
            />
            <br/>
            <RaisedButton
              type='button'
              label='Logout'
              onClick={logout}
              primary={true}
              style={{margin: 1 + 'em'}}
            />
          </CardText>
        </Card>
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    TFTPEnabled: state.getIn(['dome', 'config', 'TFTPEnabled']),
    configUpdating: state.getIn(['dome', 'config', 'updating'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    disableTFTP: () => dispatch(DomeActions.disableTFTP()),
    enableTFTP: () => dispatch(DomeActions.enableTFTP()),
    initializeConfig: () => dispatch(DomeActions.initializeConfig()),
    logout: () => dispatch(DomeActions.logout())
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(ConfigApp);
