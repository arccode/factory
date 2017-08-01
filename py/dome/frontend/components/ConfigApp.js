// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardTitle, CardText} from 'material-ui/Card';
import {connect} from 'react-redux';
import Immutable from 'immutable';
import React from 'react';
import Toggle from 'material-ui/Toggle';

import DomeActions from '../actions/domeactions';

var ConfigApp = React.createClass({
  propTypes: {
    TFTPEnabled: React.PropTypes.bool.isRequired,
    disableTFTP: React.PropTypes.func.isRequired,
    enableTFTP: React.PropTypes.func.isRequired,
    initializeConfig: React.PropTypes.func.isRequired
  },

  componentDidMount() {
    this.props.initializeConfig();
  },

  render() {
    const {
      TFTPEnabled,
      disableTFTP,
      enableTFTP,
      initializeConfig
    } = this.props;

    return (
      <div>
        <Card>
          <CardTitle title={'Config'}></CardTitle>
          <CardText>
            <Toggle
              label="TFTP server"
              toggled={TFTPEnabled}
              onToggle={TFTPEnabled ? disableTFTP : enableTFTP}
            />
          </CardText>
        </Card>
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    TFTPEnabled: state.getIn(['dome', 'TFTPEnabled'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    disableTFTP: () => dispatch(DomeActions.disableTFTP()),
    enableTFTP: () => dispatch(DomeActions.enableTFTP()),
    initializeConfig: () => dispatch(DomeActions.initializeConfig())
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(ConfigApp);
