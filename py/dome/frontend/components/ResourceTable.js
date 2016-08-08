// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import React from 'react';
import {Table, TableBody, TableHeader, TableHeaderColumn,
        TableRow, TableRowColumn} from 'material-ui/Table';

var ResourceTable = React.createClass({
  propTypes: {
    bundle: React.PropTypes.instanceOf(Immutable.Map).isRequired
  },

  render: function() {
    const {bundle, handleUpdate} = this.props;
    const resources = bundle.get('resources');

    return (
      <Table selectable={false}>
        {/* Checkboxes will be displayed by default in Material-UI, prevent
            Material-UI from showing them. */}
        <TableHeader adjustForCheckbox={false} displaySelectAll={false}>
          <TableRow>
            <TableHeaderColumn>resource</TableHeaderColumn>
            <TableHeaderColumn>version</TableHeaderColumn>
            <TableHeaderColumn>hash</TableHeaderColumn>
            <TableHeaderColumn>actions</TableHeaderColumn>
          </TableRow>
        </TableHeader>
        <TableBody displayRowCheckbox={false}>
          {resources.keySeq().toArray().map(type => {
            var resource = resources.get(type);

            // Version string often exceeds the width of the cell, and the
            // default behavior of TableRowColumn is to clip it. We need to make
            // sure that the user can see the full string.
            var style = {
              whiteSpace: 'normal',
              wordWrap: 'break-word'
            };

            return (
              <TableRow key={type}>
                <TableRowColumn style={style}>
                  {type}
                </TableRowColumn>
                <TableRowColumn style={style}>
                  {resource.get('version')}
                </TableRowColumn>
                <TableRowColumn style={style}>
                  {resource.get('hash')}
                </TableRowColumn>
                <TableRowColumn>
                  {/* TODO(littlecvr): add update button */}
                </TableRowColumn>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    );
  }
});

export default ResourceTable;
