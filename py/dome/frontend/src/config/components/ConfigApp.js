// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardText, CardTitle} from 'material-ui/Card';
import RaisedButton from 'material-ui/RaisedButton';
import Toggle from 'material-ui/Toggle';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {createStructuredSelector} from 'reselect';

import auth from '@app/auth';

import {
  disableTFTP,
  enableTFTP,
  fetchConfig,
} from '../actions';
import {
  isConfigUpdating,
  isTFTPEnabled,
} from '../selectors';

class ConfigApp extends React.Component {
  static propTypes = {
    isTFTPEnabled: PropTypes.bool.isRequired,
    isConfigUpdating: PropTypes.bool.isRequired,
    disableTFTP: PropTypes.func.isRequired,
    enableTFTP: PropTypes.func.isRequired,
    fetchConfig: PropTypes.func.isRequired,
    logout: PropTypes.func.isRequired,
  };

  componentDidMount() {
    this.props.fetchConfig();
  }

  render() {
    const {
      isTFTPEnabled,
      isConfigUpdating,
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
              toggled={isTFTPEnabled}
              onToggle={isTFTPEnabled ? disableTFTP : enableTFTP}
              disabled={isConfigUpdating}
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

const mapStateToProps = createStructuredSelector({
  isTFTPEnabled,
  isConfigUpdating,
});

const mapDispatchToProps = {
  disableTFTP,
  enableTFTP,
  fetchConfig,
  logout: auth.actions.logout,
};

export default connect(mapStateToProps, mapDispatchToProps)(ConfigApp);
