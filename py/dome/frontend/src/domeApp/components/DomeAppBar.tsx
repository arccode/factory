// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {amber300, grey300, red500} from 'material-ui/styles/colors';
import React from 'react';
import {connect} from 'react-redux';

import {RootState} from '@app/types';

import {getDomeInfo} from '../selectors';
import {DomeInfo} from '../types';

import FixedAppBar from './FixedAppBar';

const EmphasizedString: React.SFC = ({children}) => (
  <span style={{fontWeight: 'bold', color: amber300}}>{children}</span>
);

interface DomeInfoProps {
  domeInfo: DomeInfo | null;
}

const DomeInfoComponent: React.SFC<DomeInfoProps> = ({domeInfo}) => {
  const dockerVersion =
    domeInfo == null ? '(unknown)' :
      `${domeInfo.dockerImageTimestamp}` +
      `${domeInfo.dockerImageIslocal ? ' (local)' : ''}`;
  const dockerHash =
    domeInfo == null ? '(unknown)' : domeInfo.dockerImageGithash;
  return (
    <pre
      style={{
        fontSize: 'x-small',
        color: grey300,
      }}
    >
      Docker image: {dockerVersion}
      {'\n'}
      Hash: {dockerHash}
      {domeInfo && domeInfo.isDevServer && (
        <>
          {'\n'}
          <span style={{color: red500, fontWeight: 'bold'}}>DEV SERVER</span>
        </>
      )}
    </pre>
  );
};

const DomeAppBarTitle: React.SFC = () => (
  <span>
    <EmphasizedString>D</EmphasizedString>ome:
    fact<EmphasizedString>o</EmphasizedString>ry
    server <EmphasizedString>m</EmphasizedString>anagement
    consol<EmphasizedString>e</EmphasizedString>
  </span>
);

interface DomeAppBarProps {
  toggleAppMenu: () => void;
  onHeightChange: (height: number) => void;
  zDepth: number;
  domeInfo: DomeInfo | null;
}

const DomeAppBar: React.SFC<DomeAppBarProps> =
  ({toggleAppMenu, onHeightChange, zDepth, domeInfo}) => (
    <FixedAppBar
      title={<DomeAppBarTitle />}
      iconElementRight={<DomeInfoComponent domeInfo={domeInfo} />}
      onLeftIconButtonClick={toggleAppMenu}
      onHeightChange={onHeightChange}
      zDepth={zDepth}
    />
  );

const mapStateToProps = (state: RootState) => ({
  domeInfo: getDomeInfo(state),
});

export default connect(mapStateToProps)(DomeAppBar);
