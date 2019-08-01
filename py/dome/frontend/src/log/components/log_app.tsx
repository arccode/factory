// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {connect} from 'react-redux';

import project from '@app/project';
import {RootState} from '@app/types';
import {DispatchProps} from '@common/types';

import {exportLog} from '../actions';
import {LogFormData} from '../types';

import LogForm from './log_form';

type LogAppProps =
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

class LogApp extends React.Component<LogAppProps> {
  render() {
    const {
      projectName,
      exportLog,
    } = this.props;

    const startExportLog = (archive: LogFormData) => {
      exportLog(projectName,
                archive.logType,
                archive.archiveSize,
                archive.archiveUnit,
                archive.startDate,
                archive.endDate);
    };

    return (
      <LogForm onSubmit={startExportLog} />
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  projectName: project.selectors.getCurrentProject(state),
});

const mapDispatchToProps = {
  exportLog,
};

export default connect(mapStateToProps, mapDispatchToProps)(LogApp);
