// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardTitle, CardText} from 'material-ui/Card';
import {connect} from 'react-redux';
import Immutable from 'immutable';
import RaisedButton from 'material-ui/RaisedButton';
import React from 'react';
import {Table, TableBody, TableHeader, TableHeaderColumn,
        TableRow, TableRowColumn} from 'material-ui/Table';

import DomeActions from '../actions/domeactions';
import EnablingUmpireForm from './EnablingUmpireForm';
import FormNames from '../constants/FormNames';

var DashboardApp = React.createClass({
  propTypes: {
    project: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    closeEnablingUmpireForm: React.PropTypes.func.isRequired,
    disableUmpire: React.PropTypes.func.isRequired,
    enableUmpire: React.PropTypes.func.isRequired,
    enablingUmpireFormOpened: React.PropTypes.bool.isRequired,
    openEnablingUmpireForm: React.PropTypes.func.isRequired
  },

  render() {
    const {
      project,
      closeEnablingUmpireForm,
      disableUmpire,
      enableUmpire,
      enablingUmpireFormOpened,
      openEnablingUmpireForm
    } = this.props;

    return (
      <div>
        {/* TODO(littlecvr): add <ProductionLineInfoPanel /> */}

        <Card>
          <CardTitle title={'Applications'}></CardTitle>
          <CardText>
            <Table selectable={false}>
              <TableHeader adjustForCheckbox={false} displaySelectAll={false}>
                <TableRow>
                  <TableHeaderColumn>application</TableHeaderColumn>
                  <TableHeaderColumn>status</TableHeaderColumn>
                  <TableHeaderColumn>info</TableHeaderColumn>
                  <TableHeaderColumn>actions</TableHeaderColumn>
                </TableRow>
              </TableHeader>
              <TableBody displayRowCheckbox={false}>
                <TableRow>
                  <TableRowColumn>Umpire (bundle management)</TableRowColumn>
                  <TableRowColumn>
                    {project.get('umpireEnabled') && 'enabled'}
                    {!project.get('umpireEnabled') && 'disabled'}
                  </TableRowColumn>
                  <TableRowColumn>
                    {project.get('umpireEnabled') && <div>
                      host: {project.get('umpireHost')}<br />
                      port: {project.get('umpirePort')}
                    </div>}
                  </TableRowColumn>
                  <TableRowColumn>
                    {project.get('umpireEnabled') && <RaisedButton
                      label="DISABLE"
                      onClick={() => disableUmpire(project.get('name'))}
                    />}
                    {!project.get('umpireEnabled') && <RaisedButton
                      label="ENABLE"
                      onClick={openEnablingUmpireForm}
                    />}
                  </TableRowColumn>
                </TableRow>
              </TableBody>
            </Table>
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
