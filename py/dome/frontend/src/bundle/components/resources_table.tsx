// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import grey from '@material-ui/core/colors/grey';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import Typography from '@material-ui/core/Typography';
import classNames from 'classnames';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';

import {thinScrollBarX} from '@common/styles';
import {DispatchProps} from '@common/types';

import {UPDATE_RESOURCE_FORM} from '../constants';
import {Bundle} from '../types';

const styles = (theme: Theme) => createStyles({
  root: {
    display: 'grid',
    gridTemplateColumns: '1fr 2fr auto',
    width: '100%',
  },
  cell: {
    padding: theme.spacing.unit,
    display: 'flex',
    alignItems: 'center',
    borderBottom: `1px solid ${grey[300]}`,
    fontSize: theme.typography.pxToRem(13),
    ...thinScrollBarX,
  },
  actionColumn: {
    justifyContent: 'center',
  },
});

interface ResourceTableOwnProps {
  bundle: Bundle;
}

type ResourceTableProps =
  ResourceTableOwnProps &
  WithStyles<typeof styles> &
  DispatchProps<typeof mapDispatchToProps>;

class ResourceTable extends React.Component<ResourceTableProps> {
  render() {
    const {
      bundle: {name, resources},
      openUpdateResourceForm,
      classes,
    } = this.props;

    return (
      <div className={classes.root}>
        <div className={classes.cell}>
          <Typography variant="caption">
            resource
          </Typography>
        </div>
        <div className={classes.cell}>
          <Typography variant="caption">
            version
          </Typography>
        </div>
        <div
          className={classNames(classes.cell, classes.actionColumn)}
        >
          <Typography variant="caption">
            actions
          </Typography>
        </div>
        {Object.keys(resources).sort().map((key) => {
          const resource = resources[key];

          return (
            <React.Fragment key={resource.type}>
              <div className={classes.cell}>
                {resource.type}
              </div>
              <div className={classes.cell}>
                {resource.version}
              </div>
              <div className={classes.cell}>
                <Button
                  variant="outlined"
                  onClick={
                    () => openUpdateResourceForm(name, key, resource.type)
                  }
                >
                  update
                </Button>
              </div>
            </React.Fragment>
          );
        })}
      </div>
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

export default connect(null, mapDispatchToProps)(
  withStyles(styles)(ResourceTable));
