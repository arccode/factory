// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import RaisedButton from 'material-ui/RaisedButton';
import {
  Table,
  TableBody,
  TableHeader,
  TableHeaderColumn,
  TableRow,
  TableRowColumn,
} from 'material-ui/Table';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';

import {UPDATE_RESOURCE_FORM} from '../constants';
import {Bundle} from '../types';

interface ResourceTableProps {
  openUpdateResourceForm: (name: string, key: string, type: string) => any;
  bundle: Bundle;
}

class ResourceTable extends React.Component<ResourceTableProps> {
  render() {
    const {bundle: {name, resources}, openUpdateResourceForm} = this.props;

    return (
      <Table selectable={false}>
        {/* Checkboxes will be displayed by default in Material-UI, prevent
            Material-UI from showing them. */}
        <TableHeader adjustForCheckbox={false} displaySelectAll={false}>
          <TableRow>
            <TableHeaderColumn>resource</TableHeaderColumn>
            <TableHeaderColumn>version</TableHeaderColumn>
            <TableHeaderColumn>actions</TableHeaderColumn>
          </TableRow>
        </TableHeader>
        <TableBody displayRowCheckbox={false}>
          {Object.keys(resources).sort().map((key) => {
            const resource = resources[key];

            // Version string often exceeds the width of the cell, and the
            // default behavior of TableRowColumn is to clip it. We need to make
            // sure that the user can see the full string.
            const style: React.CSSProperties = {
              whiteSpace: 'normal',
              wordWrap: 'break-word',
            };

            return (
              <TableRow key={resource.type}>
                <TableRowColumn style={style}>
                  {resource.type}
                </TableRowColumn>
                <TableRowColumn style={style}>
                  {resource.version}
                </TableRowColumn>
                <TableRowColumn>
                  {
                    <RaisedButton
                      label="update"
                      onClick={
                        () => openUpdateResourceForm(name, key, resource.type)
                      }
                    />
                  }
                </TableRowColumn>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    );
  }
}

const mapDispatchToProps = {
  openUpdateResourceForm:
    (bundleName: string, resourceKey: string, resourceType: string) => (
      formDialog.actions.openForm(
        UPDATE_RESOURCE_FORM,
        // TODO(littlecvr): resourceKey are actually the same, but
        //                  resourceKey is CamelCased, resourceType is
        //                  lowercase_separated_by_underscores. We should
        //                  probably normalize the data in store so we don't
        //                  have to pass both resourceKey and resourceType
        //                  into it.
        {bundleName, resourceKey, resourceType})
    ),
};

export default connect(null, mapDispatchToProps)(ResourceTable);
