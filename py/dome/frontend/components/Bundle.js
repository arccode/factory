// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ContentCopyIcon from 'material-ui/svg-icons/content/content-copy';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import DragHandleIcon from 'material-ui/svg-icons/editor/drag-handle';
import IconButton from 'material-ui/IconButton';
import Immutable from 'immutable';
import React from 'react';
import {Card, CardTitle, CardText} from 'material-ui/Card';
import {SortableHandle} from 'react-sortable-hoc';

import ResourceTable from './ResourceTable';

var DragHandle = SortableHandle(() => (
  <IconButton
    tooltip="move this bundle"
    style={{cursor: 'move'}}
    onClick={e => e.stopPropagation()}
  >
    <DragHandleIcon />
  </IconButton>
));

var Bundle = React.createClass({
  propTypes: {
    bundle: React.PropTypes.instanceOf(Immutable.Map).isRequired
  },

  render: function() {
    const {bundle} = this.props;

    return (
      <Card className="bundle">
        <CardTitle
          title={bundle.get('name')}
          subtitle={bundle.get('note')}
          actAsExpander={true}
        >
          {/* TODO(littlecvr): top and right should be calculated */}
          <div style={{position: 'absolute', top: 18, right: 18}}>
            <div
              style={{display: 'inline-block'}}
              onClick={this.handleActivate}
            >
              <Toggle
                label={bundle.get('active') ? 'ACTIVE' : 'INACTIVE'}
                toggled={bundle.get('active')}
              />
            </div>
            {/* make some space */}
            <div style={{display: 'inline-block', width: 48}}></div>
            <DragHandle />
            <IconButton
              tooltip="copy this bundle"
              onClick={e => e.stopPropagation()}
              onTouchTap={() => console.log('not implemented')}
            >
              <ContentCopyIcon />
            </IconButton>
            <IconButton
              tooltip="delete this bundle"
              onClick={e => e.stopPropagation()}
              onTouchTap={() => console.log('not implemented')}
            >
              <DeleteIcon />
            </IconButton>
          </div>
        </CardTitle>
        <CardText expandable={true}>
          <ResourceTable bundle={bundle} />
        </CardText>
      </Card>
    );
  }
});

export default Bundle;
