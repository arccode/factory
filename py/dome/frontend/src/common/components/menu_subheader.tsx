// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import MenuItem, {MenuItemProps} from '@material-ui/core/MenuItem';
import RootRef from '@material-ui/core/RootRef';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import React from 'react';

import {Omit} from '@common/types';

const styles = (theme: Theme) => createStyles({
  subtitle: {
    ...theme.typography.subtitle1,
    color: theme.palette.grey[500],
    fontWeight: theme.typography.fontWeightMedium,
  },
});

type MenuSubheaderProps =
  Omit<MenuItemProps, 'classes'> & WithStyles<typeof styles>;

class MenuSubheader extends React.Component<MenuSubheaderProps> {
  menuItemRef: React.RefObject<HTMLLIElement>;

  constructor(props: MenuSubheaderProps) {
    super(props);
    this.menuItemRef = React.createRef();
  }

  removeFocus() {
    const menuItemDom = this.menuItemRef.current!;
    menuItemDom.removeAttribute('tabindex');
  }

  componentDidMount() {
    this.removeFocus();
  }

  componentDidUpdate() {
    this.removeFocus();
  }

  render() {
    const {classes, ...other} = this.props;
    return (
      <RootRef rootRef={this.menuItemRef}>
        <MenuItem button={false} className={classes.subtitle} {...other} />
      </RootRef>
    );
  }
}

export default withStyles(styles)(MenuSubheader);
