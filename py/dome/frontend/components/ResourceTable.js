// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import {Table, TableBody, TableHeader, TableHeaderColumn,
        TableRow, TableRowColumn} from 'material-ui/Table';
import Immutable from 'immutable';
import React from 'react';
import RaisedButton from 'material-ui/RaisedButton';

import DomeActions from '../actions/domeactions';
import FormNames from '../constants/FormNames';

var ResourceTable = React.createClass({
  propTypes: {
    handleUpdate: React.PropTypes.func.isRequired,
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
                  {/* show update button for updatable resources only */}
                  {resource.get('updatable') &&
                    <RaisedButton
                      label="update"
                      onClick={() => handleUpdate(bundle.get('name'), type)}
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
});

function mapDispatchToProps(dispatch) {
  return {
    handleUpdate: (bundleName, resourceType) => dispatch(DomeActions.openForm(
        FormNames.UPDATING_RESOURCE_FORM, {bundleName, resourceType}
    ))
  };
}

export default connect(null, mapDispatchToProps)(ResourceTable);
