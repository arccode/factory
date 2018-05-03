// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardTitle, CardText} from 'material-ui/Card';
import Divider from 'material-ui/Divider';
import {connect} from 'react-redux';
import {List, ListItem} from 'material-ui/List';
import Immutable from 'immutable';
import React from 'react';
import Subheader from 'material-ui/Subheader';
import Toggle from 'material-ui/Toggle';

import DomeActions from '../actions/domeactions';
import EnablingUmpireForm from './EnablingUmpireForm';
import FormNames from '../constants/FormNames';
import ServiceList from './ServiceList';

var DashboardApp = React.createClass({
  propTypes: {
    project: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    closeEnablingUmpireForm: React.PropTypes.func.isRequired,
    disableUmpire: React.PropTypes.func.isRequired,
    enableUmpire: React.PropTypes.func.isRequired,
    enablingUmpireFormOpened: React.PropTypes.bool.isRequired,
    openEnablingUmpireForm: React.PropTypes.func.isRequired,
  },

  handleToggle() {
    if (this.props.project.get('umpireEnabled'))
      this.props.disableUmpire(this.props.project.get('name'));
    else this.props.openEnablingUmpireForm();
  },

  render() {
    const {
      project,
      closeEnablingUmpireForm,
      enableUmpire,
      enablingUmpireFormOpened,
    } = this.props;

    const styles = {
      regularText: {
        fontSize: 1 + 'em',
        margin: 1 + 'em',
        lineHeight: 1.5 + 'em'
      }
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
                    toggled={project.get('umpireEnabled')}
                    onToggle={this.handleToggle}
                  />
                }
                primaryText='Enable Umpire'
              />
              {project.get('umpireEnabled') && project.get('umpireReady') &&
              <div>
                <Subheader>Info</Subheader>
                <Divider/>
                <div style={styles.regularText}>
                  <div>host: {project.get('umpireHost')}</div>
                  <div>port: {project.get('umpirePort')}</div>
                </div>
                <Subheader>Services</Subheader>
                <Divider/>
                  <ServiceList/>
              </div>}
            </List>
          </CardText>
        </Card>

        {/* TODO(littlecvr): add <SystemInfoPanel /> */}

        <EnablingUmpireForm
          projectName={project.get('name')}
          onCancel={closeEnablingUmpireForm}
          onConfirm={(projectName, umpireSettings) => {
            closeEnablingUmpireForm();
            enableUmpire(projectName, umpireSettings);
          }}
          opened={enablingUmpireFormOpened}
        />
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    project: state.getIn([
      'dome', 'projects', state.getIn(['dome', 'currentProject'])
    ]),
    enablingUmpireFormOpened: state.getIn([
      'dome', 'formVisibility', FormNames.ENABLING_UMPIRE_FORM
    ], false)
  };
}

function mapDispatchToProps(dispatch) {
  return {
    closeEnablingUmpireForm: () => dispatch(
        DomeActions.closeForm(FormNames.ENABLING_UMPIRE_FORM)
    ),
    disableUmpire: projectName => (
        dispatch(DomeActions.updateProject(projectName,
                                           {'umpireEnabled': false}))
    ),
    enableUmpire: (projectName, umpireSettings) => (
        dispatch(DomeActions.updateProject(projectName, Object.assign({
          'umpireEnabled': true
        }, umpireSettings)))
    ),
    openEnablingUmpireForm: () => (
        dispatch(DomeActions.openForm(FormNames.ENABLING_UMPIRE_FORM))
    )
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(DashboardApp);
