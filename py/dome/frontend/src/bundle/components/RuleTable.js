// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import ChipInput from 'material-ui-chip-input';
import {
  Table,
  TableBody,
  TableHeaderColumn,
  TableRow,
  TableRowColumn,
} from 'material-ui/Table';
import PropTypes from 'prop-types';
import React from 'react';

class RuleTable extends React.Component {
  static propTypes = {
    rules: PropTypes.object.isRequired,
    changeRules: PropTypes.func.isRequired,
  };

  handleAdd = (key, value) => {
    const rules = produce(this.props.rules, (draft) => {
      if (!(key in draft)) {
        draft[key] = [];
      }
      draft[key].push(value);
    });
    this.props.changeRules(rules);
  }

  handleDelete = (key, value) => {
    const rules = produce(this.props.rules, (draft) => {
      const index = draft[key].indexOf(value);
      if (index >= 0) {
        draft[key].splice(index, 1);
      }
    });
    this.props.changeRules(rules);
  }

  render() {
    // make sure every key exists
    const rules = {
      'macs': [],
      'serialNumbers': [],
      'mlbSerialNumbers': [],
      ...this.props.rules,
    };

    return (
      <Table selectable={false}>
        <TableBody displayRowCheckbox={false}>
          <TableRow>
            <TableHeaderColumn>MAC</TableHeaderColumn>
            <TableRowColumn>
              <ChipInput
                value={rules.macs}
                onRequestAdd={(m) => this.handleAdd('macs', m)}
                onRequestDelete={(m) => this.handleDelete('macs', m)}
              />
            </TableRowColumn>
          </TableRow>
          <TableRow>
            <TableHeaderColumn>SN</TableHeaderColumn>
            <TableRowColumn>
              <ChipInput
                value={rules.serialNumbers}
                onRequestAdd={(s) => this.handleAdd('serialNumbers', s)}
                onRequestDelete={(s) => this.handleDelete('serialNumbers', s)}
              />
            </TableRowColumn>
          </TableRow>
          <TableRow>
            <TableHeaderColumn>MLB SN</TableHeaderColumn>
            <TableRowColumn>
              <ChipInput
                value={rules.mlbSerialNumbers}
                onRequestAdd={(s) => this.handleAdd('mlbSerialNumbers', s)}
                onRequestDelete={
                  (s) => this.handleDelete('mlbSerialNumbers', s)
                }
              />
            </TableRowColumn>
          </TableRow>
        </TableBody>
      </Table>
    );
  }
}

export default RuleTable;
