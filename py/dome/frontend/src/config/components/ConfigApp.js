// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardText, CardTitle} from 'material-ui/Card';
import RaisedButton from 'material-ui/RaisedButton';
import Toggle from 'material-ui/Toggle';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import * as actions from '../actions';
import {logout} from '../../auth/actions';

class ConfigApp extends React.Component {
  static propTypes = {
    TFTPEnabled: PropTypes.bool.isRequired,
    configUpdating: PropTypes.bool.isRequired,
    disableTFTP: PropTypes.func.isRequired,
    enableTFTP: PropTypes.func.isRequired,
    initializeConfig: PropTypes.func.isRequired,
    logout: PropTypes.func.isRequired,
  };

  componentDidMount() {
    this.props.initializeConfig();
  }

  render() {
    const {
      TFTPEnabled,
      configUpdating,
      disableTFTP,
      enableTFTP,
      logout,
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
}

const mapStateToProps = (state) => {
  return {
    TFTPEnabled: state.getIn(['config', 'TFTPEnabled']),
    configUpdating: state.getIn(['config', 'updating']),
  };
};

const mapDispatchToProps = (dispatch) => {
  return {
    disableTFTP: () => dispatch(actions.disableTFTP()),
    enableTFTP: () => dispatch(actions.enableTFTP()),
    initializeConfig: () => dispatch(actions.initializeConfig()),
    logout: () => dispatch(logout()),
  };
};

export default connect(mapStateToProps, mapDispatchToProps)(ConfigApp);
