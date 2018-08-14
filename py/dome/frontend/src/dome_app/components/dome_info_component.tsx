// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {grey, red} from '@material-ui/core/colors';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import React from 'react';

import {DomeInfo} from '../types';

const styles = (theme: Theme) => createStyles({
  root: {
    fontSize: theme.typography.pxToRem(10),
    color: grey[300],
  },
  devServer: {
    color: red[500],
    fontWeight: 600,
  },
});

interface DomeInfoProps extends WithStyles<typeof styles> {
  domeInfo: DomeInfo | null;
}

const DomeInfoComponent: React.SFC<DomeInfoProps> = ({domeInfo, classes}) => {
  const dockerVersion =
    domeInfo == null ? '(unknown)' :
      `${domeInfo.dockerImageTimestamp}` +
      `${domeInfo.dockerImageIslocal ? ' (local)' : ''}`;
  const dockerHash =
    domeInfo == null ? '(unknown)' : domeInfo.dockerImageGithash;
  return (
    <pre className={classes.root}>
      Docker image: {dockerVersion}
      {'\n'}
      Hash: {dockerHash}
      {domeInfo && domeInfo.isDevServer && (
        <>
          {'\n'}
          <span className={classes.devServer}>DEV SERVER</span>
        </>
      )}
    </pre>
  );
};

export default withStyles(styles)(DomeInfoComponent);
