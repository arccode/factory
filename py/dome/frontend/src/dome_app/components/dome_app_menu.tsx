// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Drawer from '@material-ui/core/Drawer';
import MenuList from '@material-ui/core/MenuList';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import React from 'react';
import {connect} from 'react-redux';

import auth from '@app/auth';
import project from '@app/project';
import {Project} from '@app/project/types';
import {RootState} from '@app/types';

import MenuSubheader from '@common/components/menu_subheader';

import DomeAppMenuItem from './dome_app_menu_item';

const styles = (theme: Theme) => createStyles({
  toolbarSpace: theme.mixins.toolbar,
  nested: {
    paddingLeft: theme.spacing.unit * 4,
  },
});

interface DomeAppMenuProps extends WithStyles<typeof styles> {
  isLoggedIn: boolean;
  project: Project | null;
  width: number;
  open: boolean;
}

const DomeAppMenu: React.SFC<DomeAppMenuProps> = ({
  isLoggedIn,
  project,
  open,
  classes,
  width,
}) => {
  return (
    <Drawer
      variant="persistent"
      open={open}
      PaperProps={{elevation: 2, style: {width}}}
    >
      <div className={classes.toolbarSpace} />
      {isLoggedIn && (
        <MenuList disablePadding={true}>
          {project && [
            <MenuSubheader key="header">
              {project.name}
            </MenuSubheader>,
            <DomeAppMenuItem
              app="DASHBOARD_APP"
              key="DASHBOARD_APP"
              className={classes.nested}
            >
              Dashboard
            </DomeAppMenuItem>,
            <DomeAppMenuItem
              app="BUNDLES_APP"
              key="BUNDLES_APP"
              className={classes.nested}
              disabled={!project.umpireReady}
              divider={true}
            >
              Bundles {project.umpireEnabled &&
                !project.umpireReady && '(activating...)'}
            </DomeAppMenuItem>,
          ]}

          <DomeAppMenuItem app="PROJECTS_APP" divider={true}>
            Select project
          </DomeAppMenuItem>
          <DomeAppMenuItem app="CONFIG_APP">
            Config
          </DomeAppMenuItem>
        </MenuList>
      )}
    </Drawer>
  );
};

const mapStateToProps = (state: RootState) => ({
  isLoggedIn: auth.selectors.isLoggedIn(state),
  project: project.selectors.getCurrentProjectObject(state),
});

export default connect(mapStateToProps)(withStyles(styles)(DomeAppMenu));
