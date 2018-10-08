// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import CardHeader from '@material-ui/core/CardHeader';
import Divider from '@material-ui/core/Divider';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import List from '@material-ui/core/List';
import ListItem from '@material-ui/core/ListItem';
import ListSubheader from '@material-ui/core/ListSubheader';
import Switch from '@material-ui/core/Switch';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';
import project from '@app/project';
import ServiceList from '@app/service/components/service_list';
import {RootState} from '@app/types';

import {DispatchProps} from '@common/types';

import {disableUmpire, enableUmpireWithSettings} from '../actions';
import {ENABLE_UMPIRE_FORM} from '../constants';

import EnableUmpireForm from './enable_umpire_form';

type DashboardAppProps =
  ReturnType<typeof mapStateToProps> & DispatchProps<typeof mapDispatchToProps>;

class DashboardApp extends React.Component<DashboardAppProps> {
  handleToggle = () => {
    const {
      project: {umpireEnabled, name},
      disableUmpire,
      openEnableUmpireForm,
    } = this.props;
    if (umpireEnabled) {
      disableUmpire(name);
    } else {
      openEnableUmpireForm();
    }
  }

  render() {
    const {
      project,
      closeEnableUmpireForm,
      enableUmpireWithSettings,
    } = this.props;

    return (
      <>
        {/* TODO(littlecvr): add <ProductionLineInfoPanel /> */}

        <Card>
          <CardHeader title="Dashboard" />
          <CardContent>
            <FormControlLabel
              control={
                <Switch
                  color="primary"
                  checked={project.umpireEnabled}
                  disableRipple
                />
              }
              label="Enable Umpire"
              onChange={this.handleToggle}
            />
            <List>
              {project.umpireEnabled && project.umpireReady &&
                <>
                  <ListSubheader>Info</ListSubheader>
                  <Divider />
                  <ListItem>
                    port: {project.umpirePort}
                  </ListItem>
                  <ListSubheader>Services</ListSubheader>
                  <ServiceList />
                </>}
            </List>
          </CardContent>
        </Card>

        {/* TODO(littlecvr): add <SystemInfoPanel /> */}

        <EnableUmpireForm
          project={project}
          onCancel={closeEnableUmpireForm}
          onSubmit={(umpireSettings) => {
            closeEnableUmpireForm();
            enableUmpireWithSettings(project.name, umpireSettings);
          }}
        />
      </>
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  project: project.selectors.getCurrentProjectObject(state)!,
});

const mapDispatchToProps = {
  disableUmpire,
  enableUmpireWithSettings,
  openEnableUmpireForm: () => formDialog.actions.openForm(ENABLE_UMPIRE_FORM),
  closeEnableUmpireForm: () => formDialog.actions.closeForm(ENABLE_UMPIRE_FORM),
};

export default connect(mapStateToProps, mapDispatchToProps)(DashboardApp);
