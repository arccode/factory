// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardText, CardTitle} from 'material-ui/Card';
import Divider from 'material-ui/Divider';
import {List, ListItem} from 'material-ui/List';
import Subheader from 'material-ui/Subheader';
import Toggle from 'material-ui/Toggle';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';
import project from '@app/project';
import {Project, UmpireSetting} from '@app/project/types';
import ServiceList from '@app/service/components/service_list';
import {RootState} from '@app/types';

import {disableUmpire, enableUmpireWithSettings} from '../actions';
import {ENABLE_UMPIRE_FORM} from '../constants';

import EnableUmpireForm from './enable_umpire_form';

interface DashboardAppProps {
  project: Project;
  openEnableUmpireForm: () => any;
  closeEnableUmpireForm: () => any;
  disableUmpire: (name: string) => any;
  enableUmpireWithSettings: (
    name: string, setting: Partial<UmpireSetting>) => any;
}

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

    const styles = {
      warningText: {
        color: 'red',
      },
    };

    return (
      <div>
        {/* TODO(littlecvr): add <ProductionLineInfoPanel /> */}

        <Card>
          <CardTitle title={'Dashboard'} />
          <CardText>
            <List>
              <ListItem
                rightToggle={
                  <Toggle
                    toggled={project.umpireEnabled}
                    onToggle={this.handleToggle}
                  />
                }
                primaryText="Enable Umpire"
              />
              {project.umpireEnabled && project.umpireReady &&
                <>
                  <Subheader>Info</Subheader>
                  <Divider />
                  {!project.isUmpireRecent &&
                    <ListItem style={styles.warningText} disabled={true}>
                      The umpire instance is using an old version of umpire,
                      and may not function properly, please restart it by
                      disabling and re-enabling it.
                    </ListItem>}
                  <ListItem disabled={true}>
                    host: {project.umpireHost}
                  </ListItem>
                  <ListItem disabled={true}>
                    port: {project.umpirePort}
                  </ListItem>
                  <Subheader>Services</Subheader>
                  <Divider />
                  <ServiceList />
                </>}
            </List>
          </CardText>
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
      </div>
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  project: project.selectors.getCurrentProjectObject(state),
});

const mapDispatchToProps = {
  disableUmpire,
  enableUmpireWithSettings,
  openEnableUmpireForm: () => (
    formDialog.actions.openForm(ENABLE_UMPIRE_FORM)
  ),
  closeEnableUmpireForm: () => (
    formDialog.actions.closeForm(ENABLE_UMPIRE_FORM)
  ),
};

export default connect(mapStateToProps, mapDispatchToProps)(DashboardApp);
