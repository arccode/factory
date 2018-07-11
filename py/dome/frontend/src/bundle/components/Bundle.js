// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardHeader, CardText, CardTitle} from 'material-ui/Card';
import IconButton from 'material-ui/IconButton';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import DragHandleIcon from 'material-ui/svg-icons/editor/drag-handle';
import ChosenIcon from 'material-ui/svg-icons/toggle/star';
import UnchosenIcon from 'material-ui/svg-icons/toggle/star-border';
import Toggle from 'material-ui/Toggle';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';
import {SortableHandle} from 'react-sortable-hoc';
import {createSelector, createStructuredSelector} from 'reselect';

import project from '@app/project';

import {
  activateBundle,
  changeBundleRules,
  collapseBundle,
  deleteBundle,
  expandBundle,
  setBundleAsNetboot,
} from '../actions';
import {getBundleExpanded} from '../selectors';

import ResourceTable from './ResourceTable';
import RuleTable from './RuleTable';

const DragHandle = SortableHandle(() => (
  <IconButton
    tooltip="move this bundle"
    style={{cursor: 'move'}}
    onClick={(e) => e.stopPropagation()}
  >
    <DragHandleIcon />
  </IconButton>
));

class Bundle extends React.Component {
  static propTypes = {
    activateBundle: PropTypes.func.isRequired,
    changeBundleRules: PropTypes.func.isRequired,
    deleteBundle: PropTypes.func.isRequired,
    bundle: PropTypes.object.isRequired,
    projectName: PropTypes.string.isRequired,
    projectNetbootBundle: PropTypes.string,
    setBundleAsNetboot: PropTypes.func.isRequired,
    expanded: PropTypes.bool.isRequired,
    expandBundle: PropTypes.func.isRequired,
    collapseBundle: PropTypes.func.isRequired,
  };

  handleActivate = (event) => {
    event.stopPropagation();
    const {bundle: {name, active}, activateBundle} = this.props;
    activateBundle(name, !active);
  }

  toggleExpand = () => {
    const {expanded, collapseBundle, expandBundle, bundle: {name}} = this.props;
    if (expanded) {
      collapseBundle(name);
    } else {
      expandBundle(name);
    }
  }

  render() {
    const {
      bundle,
      expanded,
      projectName,
      projectNetbootBundle,
      deleteBundle,
      setBundleAsNetboot,
      changeBundleRules,
    } = this.props;

    const INACTIVE_STYLE = {
      opacity: 0.3,
    };

    return (
      <Card
        className="bundle"
        expanded={expanded}
        containerStyle={bundle.active ? {} : INACTIVE_STYLE}
      >
        <CardTitle
          title={bundle.name}
          subtitle={bundle.note}
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
                label={bundle.active ? 'ACTIVE' : 'INACTIVE'}
                toggled={bundle.active}
              />
            </div>
            {/* make some space */}
            <div style={{display: 'inline-block', width: 48}}></div>
            <DragHandle />
            <IconButton
              tooltip="delete this bundle"
              onClick={(e) => {
                e.stopPropagation();
                deleteBundle(bundle.name);
              }}
            >
              <DeleteIcon />
            </IconButton>
            <IconButton
              tooltip="use this bundle's netboot resource"
              onClick={(e) => {
                e.stopPropagation();
                setBundleAsNetboot(bundle.name, projectName);
              }}
            >
              {(projectNetbootBundle === bundle.name) ?
                  <ChosenIcon /> :
                  <UnchosenIcon />}
            </IconButton>
          </div>
        </CardTitle>
        <CardHeader title="RESOURCES" expandable={true} />
        <CardText expandable={true}>
          <ResourceTable bundle={bundle} />
        </CardText>
        <CardHeader title="RULES" expandable={true} />
        <CardText expandable={true}>
          <RuleTable
            rules={bundle.rules}
            changeRules={
              (rules) => changeBundleRules(bundle.name, rules)
            }
          />
        </CardText>
      </Card>
    );
  }
}

const mapStateToProps = createStructuredSelector({
  expanded: getBundleExpanded,
  projectName: project.selectors.getCurrentProject,
  projectNetbootBundle: createSelector(
      [project.selectors.getCurrentProjectObject],
      (project) => project.netbootBundle,
  ),
});

const mapDispatchToProps = {
  activateBundle,
  changeBundleRules,
  collapseBundle,
  deleteBundle,
  expandBundle,
  setBundleAsNetboot,
};

export default connect(mapStateToProps, mapDispatchToProps)(Bundle);
