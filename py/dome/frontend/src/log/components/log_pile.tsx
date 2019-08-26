// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Card from '@material-ui/core/Card';
import Collapse from '@material-ui/core/Collapse';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import React from 'react';
import {connect} from 'react-redux';
import {createSelector} from 'reselect';

import {RootState} from '@app/types';

import {DispatchProps} from '@common/types';

import {
  collapseLogPile,
  deleteDirectory,
  downloadLog,
  downloadLogs,
  expandLogPile,
  removeDownloadFile,
  removeDownloadFiles,
  removeLogPile,
} from '../actions';
import {
  getExpansionMap,
  getOverallDownloadStateFromStateMap,
  getPiles,
} from '../selectors';
import {
  ComponentState,
  Pile,
} from '../types';

import LogComponent from './log_component';

const styles = (theme: Theme) => createStyles({
  root: {
    marginBottom: theme.spacing.unit * 2,
  },
});

export interface LogPileOwnProps {
  pileKey: string;
  projectName: string;
}

type LogPileProps =
  LogPileOwnProps &
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

class LogPile extends React.Component<LogPileProps> {
  toggleExpand = () => {
    const {
      expanded,
      expandLogPile,
      collapseLogPile,
      pileKey,
    } = this.props;
    if (expanded) {
      collapseLogPile(pileKey);
    } else {
      expandLogPile(pileKey);
    }
  }

  retryDownloadAll = () => {
    const {
      pile: {
        downloadStateMap,
      },
      projectName,
      tempDir,
      pileKey,
      downloadLogs,
    } = this.props;
    const failedDownloads = Object.keys(downloadStateMap).filter(
        (file) => downloadStateMap[file] === 'FAILED');
    downloadLogs(projectName, tempDir, failedDownloads, pileKey);
  }

  retryDownloadFile = (file: string) => {
    const {
      projectName,
      tempDir,
      pileKey,
      overallDownloadState,
    } = this.props;
    downloadLog(projectName, tempDir, file, pileKey);
    if (overallDownloadState === 'SUCCEEDED') {
      deleteDirectory(projectName, tempDir);
    }
  }

  checkAndRemoveFailedLogPile = () => {
    const {
      removeLogPile,
      tempDir,
      projectName,
      pileKey,
    } = this.props;
    removeLogPile(pileKey);
    deleteDirectory(projectName, tempDir);
  }

  checkAndRemoveDownloadFiles = () => {
    const {
      pileKey,
      removeDownloadFiles,
      projectName,
      tempDir,
    } = this.props;
    removeDownloadFiles(pileKey);
    deleteDirectory(projectName, tempDir);
  }

  checkAndRemoveDownloadFile = (file: string) => {
    const {
      removeDownloadFile,
      overallDownloadState,
      pileKey,
      tempDir,
      projectName,
    } = this.props;
    removeDownloadFile(pileKey, file);
    if (overallDownloadState === 'SUCCEEDED') {
      deleteDirectory(projectName, tempDir);
    }
  }

  render() {
    const {
      classes,
      projectName,
      expanded,
      pile: {
        title,
        compressState,
        compressReports,
        downloadStateMap,
      },
      tempDir,
      pileKey,
      pileState,
      downloadLog,
      downloadProgress,
      overallDownloadState,
    } = this.props;

    return (
      <Card className={classes.root}>
        <LogComponent
          message={title}
          componentType="header"
          componentState={pileState}
          remove={this.checkAndRemoveFailedLogPile}
          toggleExpand={this.toggleExpand}
          expanded={expanded}
        />
        <Collapse in={expanded}>
          <LogComponent
            message="compress"
            componentType="item"
            componentState={compressState}
          />

          {compressReports.map((report) => (
              <LogComponent
                key={report}
                message={report}
                componentType="list-item"
                componentState="REPORT"
              />
            ))
          }

          <LogComponent
            message="download"
            componentType="item"
            progress={downloadProgress}
            componentState={overallDownloadState}
            retry={this.retryDownloadAll}
            remove={this.checkAndRemoveDownloadFiles}
          />

          {Object.keys(downloadStateMap).map((file) => (
              <LogComponent
                key={file}
                message={`${projectName}-${file}`}
                componentType="list-item"
                componentState={downloadStateMap[file]}
                retry={() => downloadLog(projectName,
                                         tempDir,
                                         file,
                                         pileKey)}
                remove={() => this.checkAndRemoveDownloadFile(file)}
              />
            ))
          }
        </Collapse>
      </Card>
    );
  }
}

const getPile =
  (state: RootState, props: LogPileOwnProps): Pile =>
    getPiles(state)[props.pileKey];

const getTempDir = createSelector(
  getPile,
  (pile) => pile.tempDir,
);

const getCompressState = createSelector(
  getPile,
  (pile) => pile.compressState,
);

const getDownloadStateMap = createSelector(
  getPile,
  (pile) => pile.downloadStateMap,
);

const getOverallDownloadState = createSelector(
  getDownloadStateMap,
  (downloadStateMap) =>
    getOverallDownloadStateFromStateMap(downloadStateMap),
);

const getPileState = createSelector(
  [getCompressState, getOverallDownloadState],
  (compressState, overallDownloadState): ComponentState => {
    if (compressState === 'PROCESSING' ||
        overallDownloadState === 'PROCESSING') {
      return 'PROCESSING';
    } else if (compressState === 'FAILED' ||
               overallDownloadState === 'FAILED') {
      return 'FAILED';
    } else {
      return 'SUCCEEDED';
    }
  },
);

const getDownloadProgress = createSelector(
  getDownloadStateMap,
  (downloadStateMap) => {
    const numSuccessedDownloads = Object.values(downloadStateMap).filter(
      (value) => value === 'SUCCEEDED').length;
    const numDownloads = Object.keys(downloadStateMap).length;
    return numDownloads ?
        100 * numSuccessedDownloads / numDownloads : 0;
  },
);

const mapStateToProps =
  (state: RootState, ownProps: LogPileOwnProps) => ({
    pile: getPile(state, ownProps),
    expanded: getExpansionMap(state)[ownProps.pileKey],
    tempDir: getTempDir(state, ownProps),
    pileState: getPileState(state, ownProps),
    downloadProgress: getDownloadProgress(state, ownProps),
    overallDownloadState: getOverallDownloadState(state, ownProps),
  });

const mapDispatchToProps = {
  expandLogPile,
  collapseLogPile,
  removeLogPile,
  downloadLog,
  downloadLogs,
  removeDownloadFile,
  removeDownloadFiles,
};

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(LogPile));
