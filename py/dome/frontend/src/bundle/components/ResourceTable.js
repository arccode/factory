// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import RaisedButton from 'material-ui/RaisedButton';
import {
  Table,
  TableBody,
  TableHeader,
  TableHeaderColumn,
  TableRow,
  TableRowColumn,
} from 'material-ui/Table';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/formDialog';

import {UPDATING_RESOURCE_FORM} from '../constants';

class ResourceTable extends React.Component {
  static propTypes = {
    openUpdatingResourceForm: PropTypes.func.isRequired,
    bundle: PropTypes.instanceOf(Immutable.Map).isRequired,
  };

  render() {
    const {bundle, openUpdatingResourceForm} = this.props;
    const resources = bundle.get('resources');

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
          {resources.keySeq().sort().toArray().map((key) => {
            const resource = resources.get(key);

            // Version string often exceeds the width of the cell, and the
            // default behavior of TableRowColumn is to clip it. We need to make
            // sure that the user can see the full string.
            const style = {
              whiteSpace: 'normal',
              wordWrap: 'break-word',
            };

            return (
              <TableRow key={resource.get('type')}>
                <TableRowColumn style={style}>
                  {resource.get('type')}
                </TableRowColumn>
                <TableRowColumn style={style}>
                  {resource.get('version')}
                </TableRowColumn>
                <TableRowColumn>
                  {
                    <RaisedButton
                      label='update'
                      onClick={() => openUpdatingResourceForm(
                          bundle.get('name'), key, resource.get('type')
                      )}
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
  openUpdatingResourceForm: (bundleName, resourceKey, resourceType) => (
    formDialog.actions.openForm(
        UPDATING_RESOURCE_FORM,
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
