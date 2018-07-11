// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardText, CardTitle} from 'material-ui/Card';
import Divider from 'material-ui/Divider';
import {List, ListItem} from 'material-ui/List';
import Subheader from 'material-ui/Subheader';
import Toggle from 'material-ui/Toggle';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {createStructuredSelector} from 'reselect';

import formDialog from '@app/formDialog';
import project from '@app/project';
import ServiceList from '@app/service/components/ServiceList';

import {disableUmpire, enableUmpireWithSettings} from '../actions';
import {ENABLING_UMPIRE_FORM} from '../constants';

import EnablingUmpireForm from './EnablingUmpireForm';

class DashboardApp extends React.Component {
  static propTypes = {
    project: PropTypes.object.isRequired,
    closeEnablingUmpireForm: PropTypes.func.isRequired,
    disableUmpire: PropTypes.func.isRequired,
    enableUmpireWithSettings: PropTypes.func.isRequired,
    openEnablingUmpireForm: PropTypes.func.isRequired,
  };

  handleToggle = () => {
    const {
      project: {umpireEnabled, name},
      disableUmpire,
      openEnablingUmpireForm,
    } = this.props;
    if (umpireEnabled) {
      disableUmpire(name);
    } else {
      openEnablingUmpireForm();
    }
  }

  render() {
    const {
      project,
      closeEnablingUmpireForm,
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
          <CardTitle title={'Dashboard'}></CardTitle>
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
                <Divider/>
                {!project.isUmpireRecent &&
                <ListItem style={styles.warningText} disabled={true}>
                  The umpire instance is using an old version of umpire, and
                  may not function properly, please restart it by disabling and
                  re-enabling it.
                </ListItem>}
                <ListItem disabled={true}>
                  host: {project.umpireHost}
                </ListItem>
                <ListItem disabled={true}>
                  port: {project.umpirePort}
                </ListItem>
                <Subheader>Services</Subheader>
                <Divider/>
                <ServiceList/>
              </>}
            </List>
          </CardText>
        </Card>

        {/* TODO(littlecvr): add <SystemInfoPanel /> */}

        <EnablingUmpireForm
          projectName={project.name}
          onCancel={closeEnablingUmpireForm}
          onSubmit={(umpireSettings) => {
            closeEnablingUmpireForm();
            enableUmpireWithSettings(project.name, umpireSettings);
          }}
        />
      </div>
    );
  }
}

const mapStateToProps = createStructuredSelector({
  project: project.selectors.getCurrentProjectObject,
});

const mapDispatchToProps = {
  disableUmpire,
  enableUmpireWithSettings,
  openEnablingUmpireForm: () => (
    formDialog.actions.openForm(ENABLING_UMPIRE_FORM)
  ),
  closeEnablingUmpireForm: () => (
    formDialog.actions.closeForm(ENABLING_UMPIRE_FORM)
  ),
};

export default connect(mapStateToProps, mapDispatchToProps)(DashboardApp);
