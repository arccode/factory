// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import Collapse from '@material-ui/core/Collapse';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import IconButton from '@material-ui/core/IconButton';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import Switch from '@material-ui/core/Switch';
import Tooltip from '@material-ui/core/Tooltip';
import Typography from '@material-ui/core/Typography';
import DeleteIcon from '@material-ui/icons/Delete';
import DragHandleIcon from '@material-ui/icons/DragHandle';
import StarIcon from '@material-ui/icons/Star';
import StarBorderIcon from '@material-ui/icons/StarBorder';
import classNames from 'classnames';
import React from 'react';
import {connect} from 'react-redux';
import {SortableHandle} from 'react-sortable-hoc';

import project from '@app/project';
import {RootState} from '@app/types';

import {DispatchProps} from '@common/types';

import {
  activateBundle,
  collapseBundle,
  deleteBundle,
  expandBundle,
  setBundleAsNetboot,
} from '../actions';
import {getExpandedMap} from '../selectors';
import {Bundle} from '../types';

import ResourceTable from './resources_table';

const DragHandle = SortableHandle(() => (
  <Tooltip title="move this bundle">
    <IconButton disableRipple style={{cursor: 'move'}}>
      <DragHandleIcon />
    </IconButton>
  </Tooltip>
));

const styles = (theme: Theme) => createStyles({
  root: {
    marginBottom: theme.spacing.unit * 2,
  },
  inactive: {
    opacity: 0.3,
  },
  header: {
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
  },
  headerText: {
    flex: 1,
  },
  activeSwitch: {
    marginLeft: 0,
    marginRight: theme.spacing.unit * 2,
  },
});

export interface BundleComponentOwnProps {
  bundle: Bundle;
  bundles: Bundle[];
}

type BundleComponentProps =
  BundleComponentOwnProps &
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

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
      bundles,
      expanded,
      projectName,
      projectNetbootBundle,
      deleteBundle,
      setBundleAsNetboot,
      classes,
    } = this.props;

    // Disable the toggle when there's only one active bundle left.
    const toggleDisabled =
      bundle.active && bundles.filter((b) => b.active).length === 1;

    return (
      <Card
        className={classNames(classes.root, !bundle.active && classes.inactive)}
      >
        <CardContent className={classes.header} onClick={this.toggleExpand}>
          <div className={classes.headerText}>
            <Typography variant="h5">{bundle.name}</Typography>
            <Typography variant="caption">{bundle.note}</Typography>
          </div>
          <FormControlLabel
            control={<Switch
              color="primary"
              checked={bundle.active}
              disabled={toggleDisabled}
            />}
            label={bundle.active ? 'ACTIVE' : 'INACTIVE'}
            labelPlacement="start"
            onClick={(e) => e.stopPropagation()}
            onChange={this.handleActivate}
            className={classes.activeSwitch}
          />
          <DragHandle />
          <Tooltip title="delete this bundle">
            <IconButton
              onClick={(e) => {
                e.stopPropagation();
                deleteBundle(bundle.name);
              }}
            >
              <DeleteIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="use this bundle's netboot resource">
            <IconButton
              onClick={(e) => {
                e.stopPropagation();
                setBundleAsNetboot(bundle.name, projectName);
              }}
            >
              {(projectNetbootBundle === bundle.name) ?
                <StarIcon /> :
                <StarBorderIcon />}
            </IconButton>
          </Tooltip>
        </CardContent>
        <Collapse in={expanded}>
          <CardContent>
            <Typography variant="subtitle1" gutterBottom>RESOURCES</Typography>
            <Typography variant="caption">The uploaded resources should have
              the corresponding type or the compressed version (gzip/bzip2/xz
              compressed tarball) of the corresponding type.
            </Typography>
            <ResourceTable bundle={bundle} projectName={projectName} />
          </CardContent>
        </Collapse>
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
  collapseBundle,
  deleteBundle,
  expandBundle,
  setBundleAsNetboot,
};

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(BundleComponent));
