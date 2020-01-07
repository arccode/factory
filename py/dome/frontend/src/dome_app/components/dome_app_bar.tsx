// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import AppBar from '@material-ui/core/AppBar';
import {amber} from '@material-ui/core/colors';
import IconButton from '@material-ui/core/IconButton';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import Toolbar from '@material-ui/core/Toolbar';
import Typography from '@material-ui/core/Typography';
import MenuIcon from '@material-ui/icons/Menu';
import React from 'react';
import {connect} from 'react-redux';

import {RootState} from '@app/types';

import {getDomeInfo} from '../selectors';

import DomeInfoComponent from './dome_info_component';

const EmphasizedString: React.SFC = ({children}) => (
  <span style={{fontWeight: 'bold', color: amber[300]}}>{children}</span>
);

const DomeAppBarTitle: React.SFC = () => (
  <Typography variant="h6" color="inherit">
    <EmphasizedString>D</EmphasizedString>ome:
    fact<EmphasizedString>o</EmphasizedString>ry
    server <EmphasizedString>m</EmphasizedString>anagement
    consol<EmphasizedString>e</EmphasizedString>
  </Typography>
);

const styles = (theme: Theme) => createStyles({
  appBar: {
    zIndex: theme.zIndex.drawer + 1,
  },
  gutters: {
    // TODO(pihsun): We should be able to use jss-expand here, but the type
    // definition for jss plugins is not completed yet. Manually adding the
    // 'px' for now. We probably can use jss-expand after
    // https://github.com/cssinjs/jss/issues/776 is resolved.
    padding: `0 ${theme.spacing.unit}px`,
  },
  title: {
    padding: `0 ${theme.spacing.unit}px`,
    flex: 1,
  },
});

interface DomeAppBarOwnProps {
  toggleAppMenu: () => void;
}

type DomeAppBarProps =
  DomeAppBarOwnProps &
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps>;

const DomeAppBar: React.SFC<DomeAppBarProps> =
  ({toggleAppMenu, domeInfo, classes}) => (
    <AppBar position="sticky" className={classes.appBar}>
      <Toolbar classes={{gutters: classes.gutters}}>
        <IconButton color="inherit" onClick={toggleAppMenu}>
          <MenuIcon />
        </IconButton>
        <div className={classes.title}>
          <DomeAppBarTitle />
        </div>
        <DomeInfoComponent domeInfo={domeInfo} />
      </Toolbar>
    </AppBar>
  );

const mapStateToProps = (state: RootState) => ({
  domeInfo: getDomeInfo(state),
});

export default connect(mapStateToProps)(withStyles(styles)(DomeAppBar));
