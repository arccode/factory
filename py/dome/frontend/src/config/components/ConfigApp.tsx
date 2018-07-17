// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardText, CardTitle} from 'material-ui/Card';
import RaisedButton from 'material-ui/RaisedButton';
import Toggle from 'material-ui/Toggle';
import React from 'react';
import {connect} from 'react-redux';

import auth from '@app/auth';
import {RootState} from '@app/types';

import {
  disableTftp,
  enableTftp,
  fetchConfig,
} from '../actions';
import {
  isConfigUpdating,
  isTftpEnabled,
} from '../selectors';

interface ConfigAppProps {
  isTftpEnabled: boolean;
  isConfigUpdating: boolean;
  disableTftp: () => any;
  enableTftp: () => any;
  fetchConfig: () => any;
  logout: () => any;
}

class ConfigApp extends React.Component<ConfigAppProps> {
  componentDidMount() {
    this.props.fetchConfig();
  }

  render() {
    const {
      isTftpEnabled,
      isConfigUpdating,
      disableTftp,
      enableTftp,
      logout,
    } = this.props;

    return (
      <div>
        <Card>
          <CardTitle title="Config" />
          <CardText>
            <Toggle
              label="TFTP server"
              toggled={isTftpEnabled}
              onToggle={isTftpEnabled ? disableTftp : enableTftp}
              disabled={isConfigUpdating}
            />
            <br/>
            <RaisedButton
              type="button"
              label="Logout"
              onClick={logout}
              primary={true}
              style={{margin: '1em'}}
            />
          </CardText>
        </Card>
      </div>
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  isTftpEnabled: isTftpEnabled(state),
  isConfigUpdating: isConfigUpdating(state),
});

const mapDispatchToProps = {
  disableTftp,
  enableTftp,
  fetchConfig,
  logout: auth.actions.logout,
};

export default connect(mapStateToProps, mapDispatchToProps)(ConfigApp);
