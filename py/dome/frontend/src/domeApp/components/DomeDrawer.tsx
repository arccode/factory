// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Divider from 'material-ui/Divider';
import Drawer from 'material-ui/Drawer';
import MenuItem from 'material-ui/MenuItem';
import Subheader from 'material-ui/Subheader';
import React from 'react';
import {connect} from 'react-redux';

import auth from '@app/auth';
import project from '@app/project';
import {Project} from '@app/project/types';
import {RootState} from '@app/types';

import {switchApp} from '../actions';
import {AppName} from '../types';

const PROJECT_MENU_ITEM_PADDING_LEFT = 36;

interface DomeAppProps {
  isLoggedIn: boolean;
  project: Project | null;
  switchApp: (app: AppName) => any;
  top: number;
  width: number;
  open: boolean;
  zDepth: number;
}

const DomeDrawer: React.SFC<DomeAppProps> = ({
  isLoggedIn,
  switchApp,
  project,
  top,
  width,
  open,
  zDepth,
}) => (
    <Drawer
      docked={true}
      width={width}
      open={open}
      // Need to set "top" to avoid covering (or being covered by) the
      // AppBar, see https://github.com/callemall/material-ui/issues/957.
      // Setting zIndex is also needed because zDepth does not actually
      // affect zIndex, and not setting it would make this drawer covers the
      // shadow of AppBar.
      containerStyle={{top, zIndex: 1000}}
      zDepth={zDepth}
    >
      {isLoggedIn && <div>
        {project && (
          <>
            <Subheader>{project.name}</Subheader>
            <MenuItem
              onClick={() => switchApp('DASHBOARD_APP')}
              innerDivStyle={{paddingLeft: PROJECT_MENU_ITEM_PADDING_LEFT}}
            >
              Dashboard
            </MenuItem>
            <MenuItem
              onClick={() => switchApp('BUNDLES_APP')}
              innerDivStyle={{paddingLeft: PROJECT_MENU_ITEM_PADDING_LEFT}}
              disabled={!project.umpireReady}
            >
              Bundles {project.umpireEnabled &&
                !project.umpireReady && '(activating...)'}
            </MenuItem>
            <Divider />
          </>
        )}

        <MenuItem onClick={() => switchApp('PROJECTS_APP')}>
          Change project
          </MenuItem>
        <Divider />
        <MenuItem onClick={() => switchApp('CONFIG_APP')}>
          Config
          </MenuItem>
      </div>}
    </Drawer>
  );

const mapStateToProps = (state: RootState) => ({
  isLoggedIn: auth.selectors.isLoggedIn(state),
  project: project.selectors.getCurrentProjectObject(state),
});

const mapDispatchToProps = {
  switchApp,
};

export default connect(mapStateToProps, mapDispatchToProps)(DomeDrawer);
