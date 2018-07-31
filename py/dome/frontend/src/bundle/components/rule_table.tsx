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
import React from 'react';

import {RuleKey, Rules} from '../types';

interface RuleTableProps {
  rules: Partial<Rules>;
  changeRules: (rules: Partial<Rules>) => void;
}

class RuleTable extends React.Component<RuleTableProps> {
  handleAdd = (key: RuleKey, value: string) => {
    const rules = produce(this.props.rules, (draft) => {
      draft[key] = [...(draft[key] || []), value];
    });
    this.props.changeRules(rules);
  }

  handleDelete = (key: RuleKey, value: string) => {
    const rules = produce(this.props.rules, (draft) => {
      const values = draft[key];
      if (!values) return;
      const index = values.indexOf(value);
      if (index >= 0) {
        values.splice(index, 1);
      }
    });
    this.props.changeRules(rules);
  }

  render() {
    const {rules} = this.props;

    return (
      <Table selectable={false}>
        <TableBody displayRowCheckbox={false}>
          <TableRow>
            <TableHeaderColumn>MAC</TableHeaderColumn>
            <TableRowColumn>
              <ChipInput
                value={rules.macs || []}
                onRequestAdd={(m) => this.handleAdd('macs', m)}
                onRequestDelete={(m) => this.handleDelete('macs', m)}
              />
            </TableRowColumn>
          </TableRow>
          <TableRow>
            <TableHeaderColumn>SN</TableHeaderColumn>
            <TableRowColumn>
              <ChipInput
                value={rules.serialNumbers || []}
                onRequestAdd={(s) => this.handleAdd('serialNumbers', s)}
                onRequestDelete={(s) => this.handleDelete('serialNumbers', s)}
              />
            </TableRowColumn>
          </TableRow>
          <TableRow>
            <TableHeaderColumn>MLB SN</TableHeaderColumn>
            <TableRowColumn>
              <ChipInput
                value={rules.mlbSerialNumbers || []}
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
