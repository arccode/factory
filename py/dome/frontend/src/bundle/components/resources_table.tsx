// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import grey from '@material-ui/core/colors/grey';
import IconButton from '@material-ui/core/IconButton';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import Typography from '@material-ui/core/Typography';
import Download from '@material-ui/icons/GetApp';
import Update from '@material-ui/icons/Publish';
import classNames from 'classnames';
import React from 'react';
import {connect} from 'react-redux';

import formDialog from '@app/form_dialog';

import {thinScrollBarX} from '@common/styles';
import {DispatchProps} from '@common/types';

import {downloadResource} from '../actions';
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
  projectName: string;
}

type ResourceTableProps =
  ResourceTableOwnProps &
  WithStyles<typeof styles> &
  DispatchProps<typeof mapDispatchToProps>;

class ResourceTable extends React.Component<ResourceTableProps> {
  render() {
    const {
      bundle: {name, resources},
      projectName,
      openUpdateResourceForm,
      classes,
    } = this.props;

    const downloadableResources =
        /^toolkit(_config)?|hwid|firmware|complete|netboot_.*|lsb_factory$/;

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
                {resource.type} ({resourceNameToFileType[resource.type]})
              </div>
              <div className={classes.cell}>
                {resource.version}
              </div>
              <div className={classes.cell}>
                <IconButton
                  onClick={
                    () => openUpdateResourceForm(name, key, resource.type)
                  }
                >
                  <Update />
                </IconButton>

                {(!downloadableResources.test(resource.type) ||
                  resource.version === 'N/A') ?
                  <span /> :
                  <IconButton
                    onClick={
                        () => this.props.downloadResource(
                        projectName, name, resource.type)}
                  >
                    <Download />
                  </IconButton>}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    );
  }
}

const resourceNameToFileType : Record<string, string> = {
    'complete': '*.sh',
    'firmware': 'chromeos-firmwareupdate',
    'hwid': 'hwid_v3_bundle_*.sh',
    'netboot_cmdline': 'cmdline',
    'netboot_firmware': '*.net.bin',
    'netboot_kernel': 'vmlinu*',
    'project_config': '*.tar.gz',
    'release_image': '*.bin',
    'test_image': '*.bin',
    'toolkit': '*.run',
};

const mapDispatchToProps = {
  downloadResource,
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
