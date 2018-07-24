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
import React from 'react';
import {connect} from 'react-redux';
import {SortableHandle} from 'react-sortable-hoc';

import project from '@app/project';
import {RootState} from '@app/types';

import {
  activateBundle,
  changeBundleRules,
  collapseBundle,
  deleteBundle,
  expandBundle,
  setBundleAsNetboot,
} from '../actions';
import {getExpandedMap} from '../selectors';
import {Bundle, Rules} from '../types';

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

export interface BundleComponentOwnProps {
  bundle: Bundle;
}

interface BundleComponentProps extends BundleComponentOwnProps {
  activateBundle: (name: string, active: boolean) => any;
  changeBundleRules: (name: string, rules: Partial<Rules>) => any;
  deleteBundle: (name: string) => any;
  setBundleAsNetboot: (name: string, projectName: string) => any;
  expandBundle: (name: string) => any;
  collapseBundle: (name: string) => any;
  projectName: string;
  projectNetbootBundle: string | null;
  expanded: boolean;
}

class BundleComponent extends React.Component<BundleComponentProps> {
  handleActivate = () => {
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
          style={{cursor: 'pointer'}}
          // @ts-ignore The type for material-ui does not contain DOM
          // attributes, but the implementation actually pass all other props
          // onto the root div itself.
          // TODO(pihsun): This should be solved after we upgrade to use
          // Material-UI v1.
          onClick={this.toggleExpand}
        >
          {/* TODO(littlecvr): top and right should be calculated */}
          <div style={{position: 'absolute', top: 18, right: 18}}>
            <div
              style={{display: 'inline-block'}}
              onClick={(e) => {
                e.stopPropagation();
                this.handleActivate();
              }}
            >
              <Toggle
                label={bundle.active ? 'ACTIVE' : 'INACTIVE'}
                toggled={bundle.active}
              />
            </div>
            {/* make some space */}
            <div style={{display: 'inline-block', width: 48}} />
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

const mapStateToProps =
  (state: RootState, ownProps: BundleComponentOwnProps) => ({
    expanded: getExpandedMap(state)[ownProps.bundle.name],
    projectName: project.selectors.getCurrentProject(state),
    projectNetbootBundle:
      project.selectors.getCurrentProjectObject(state)!.netbootBundle,
  });

const mapDispatchToProps = {
  activateBundle,
  changeBundleRules,
  collapseBundle,
  deleteBundle,
  expandBundle,
  setBundleAsNetboot,
};

export default connect(mapStateToProps, mapDispatchToProps)(BundleComponent);
