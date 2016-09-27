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
    board: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    closeEnablingUmpireForm: React.PropTypes.func.isRequired,
    disableUmpire: React.PropTypes.func.isRequired,
    enableUmpire: React.PropTypes.func.isRequired,
    enablingUmpireFormOpened: React.PropTypes.bool.isRequired,
    openEnablingUmpireForm: React.PropTypes.func.isRequired
  },

  render() {
    const {
      board,
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
                    {board.get('umpire_enabled') && 'enabled'}
                    {!board.get('umpire_enabled') && 'disabled'}
                  </TableRowColumn>
                  <TableRowColumn>
                    {board.get('umpire_enabled') && <div>
                      host: {board.get('umpire_host')}<br />
                      port: {board.get('umpire_port')}
                    </div>}
                  </TableRowColumn>
                  <TableRowColumn>
                    {board.get('umpire_enabled') && <RaisedButton
                      label="DISABLE"
                      onClick={() => disableUmpire(board.get('name'))}
                    />}
                    {!board.get('umpire_enabled') && <RaisedButton
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
          boardName={board.get('name')}
          onCancel={closeEnablingUmpireForm}
          onConfirm={(boardName, umpireSettings) => {
            closeEnablingUmpireForm();
            enableUmpire(boardName, umpireSettings);
          }}
          opened={enablingUmpireFormOpened}
        />
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    board: state.getIn([
      'dome', 'boards', state.getIn(['dome', 'currentBoard'])
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
    disableUmpire: boardName => (
        dispatch(DomeActions.updateBoard(boardName, {'umpire_enabled': false}))
    ),
    enableUmpire: (boardName, umpireSettings) => (
        dispatch(DomeActions.updateBoard(boardName, Object.assign({
          // TODO(littlecvr): should use CamelCase
          'umpire_enabled': true
        }, umpireSettings)))
    ),
    openEnablingUmpireForm: () => (
        dispatch(DomeActions.openForm(FormNames.ENABLING_UMPIRE_FORM))
    )
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(DashboardApp);
