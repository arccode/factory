// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import MenuItem, {MenuItemProps} from '@material-ui/core/MenuItem';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import React from 'react';
import {connect} from 'react-redux';

import {RootState} from '@app/types';

import {DispatchProps, Omit} from '@common/types';

import {switchApp} from '../actions';
import {getCurrentApp} from '../selectors';
import {AppName} from '../types';

const styles = (theme: Theme) => createStyles({
  selected: {
    backgroundColor: 'initial',
    fontWeight: theme.typography.fontWeightMedium,
  },
});

interface DomeAppMenuItemOwnProps {
  app: AppName;
}

type DomeAppMenuItemProps =
  DomeAppMenuItemOwnProps &
  Omit<MenuItemProps, 'classes'> &
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

const DomeAppMenuItem: React.SFC<DomeAppMenuItemProps> = ({
  children,
  app,
  currentApp,
  switchApp,
  ...other
}) => (
  <MenuItem
    key={app}
    selected={currentApp === app}
    onClick={() => switchApp(app)}
    {...other}
  >
    {children}
  </MenuItem>
);

const mapStateToProps = (state: RootState) => ({
  currentApp: getCurrentApp(state),
});

const mapDispatchToProps = {
  switchApp,
};

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(DomeAppMenuItem));
