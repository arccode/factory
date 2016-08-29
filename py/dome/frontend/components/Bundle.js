// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ContentCopyIcon from 'material-ui/svg-icons/content/content-copy';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import DragHandleIcon from 'material-ui/svg-icons/editor/drag-handle';
import IconButton from 'material-ui/IconButton';
import Immutable from 'immutable';
import React from 'react';
import Toggle from 'material-ui/Toggle';
import {connect} from 'react-redux';
import {Card, CardTitle, CardText} from 'material-ui/Card';
import {SortableHandle} from 'react-sortable-hoc';

import BundlesActions from '../actions/bundles';
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

  handleActivate(event) {
    event.stopPropagation();
    const {bundle} = this.props;
    this.props.activateBundle(bundle.get('name'), !bundle.get('active'));
  },

  toggleExpand() {
    this.setState({expanded: !this.state.expanded});
  },

  getInitialState() {
    return {
      expanded: false,
    };
  },

  render() {
    const {bundle, deleteBundle} = this.props;

    const INACTIVE_STYLE = {
      opacity: 0.3
    };

    return (
      <Card
        className="bundle"
        expanded={this.state.expanded}
        containerStyle={bundle.get('active') ? {} : INACTIVE_STYLE}
      >
        <CardTitle
          title={bundle.get('name')}
          subtitle={bundle.get('note')}
          // Cannot use actAsExpander here, need to implement ourselves. The
          // Toggle below from Material-UI somewhat would not capture the click
          // event before CardTitle. If not using this way, when the user clicks
          // on the Toggle (which should only change the state of the Toggle),
          // the Card will also be affected (expanded or collapsed).
          onClick={this.toggleExpand}
          style={{cursor: 'pointer'}}
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
              onTouchTap={() => deleteBundle(bundle.get('name'))}
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

function mapDispatchToProps(dispatch) {
  return {
    activateBundle: (name, active) =>
        dispatch(BundlesActions.activateBundle(name, active)),
    deleteBundle: name => dispatch(BundlesActions.deleteBundle(name))
  };
}

export default connect(null, mapDispatchToProps)(Bundle);
