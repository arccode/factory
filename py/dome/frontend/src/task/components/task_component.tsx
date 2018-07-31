// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {CardText} from 'material-ui/Card';
import CircularProgress from 'material-ui/CircularProgress';
import IconButton from 'material-ui/IconButton';
import {grey700} from 'material-ui/styles/colors';
import RunningIcon from 'material-ui/svg-icons/action/autorenew';
import DismissIcon from 'material-ui/svg-icons/action/check-circle';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import ErrorIcon from 'material-ui/svg-icons/alert/error';
import React from 'react';

import {assertNotReachable} from '@common/utils';

import {isCancellable} from '../constants';
import {TaskProgress, TaskState} from '../types';

interface TaskProps {
  state: TaskState;
  progress: TaskProgress;
  description: string;
  dismiss: () => void;
  retry: () => void;
  cancel: () => void;
}

const formatProgress = ({uploadedFiles, totalFiles}: TaskProgress) => (
  `Uploading file (${uploadedFiles + 1}/${totalFiles})`
);

const Task: React.SFC<TaskProps> = ({
  state,
  progress,
  description,
  cancel,
  dismiss,
  retry,
}) => {
  let actionButton;
  switch (state) {
    case 'WAITING':
      actionButton = (
        <IconButton tooltip="waiting">
          <RunningIcon />
        </IconButton>
      );
      break;
    case 'RUNNING_UPLOAD_FILE':
      actionButton = (
        <IconButton tooltip={formatProgress(progress)}>
          <CircularProgress
            mode="determinate"
            max={progress.totalSize}
            value={progress.uploadedSize}
            size={20}
          />
        </IconButton>
      );
      break;
    case 'RUNNING_WAIT_RESPONSE':
      // There's a bug in the CircularProgress implementation, so if a
      // determinate node is reused as indeterminate one, the animation would
      // not be run. To prevent React from reusing the node from
      // RUNNING_UPLOAD_FILE, we wrap the CircularProgress in an extra div.
      actionButton = (
        <IconButton tooltip="Waiting response">
          <div>
            <CircularProgress
              mode="indeterminate"
              size={20}
            />
          </div>
        </IconButton>
      );
      break;
    case 'SUCCEEDED':
      actionButton = (
        <IconButton
          tooltip="dismiss"
          onClick={dismiss}
          iconStyle={{fill: 'green'}}
        >
          <DismissIcon />
        </IconButton>
      );
      break;
    case 'FAILED':
      actionButton = (
        <IconButton
          tooltip="retry"
          onClick={retry}
          iconStyle={{fill: 'red'}}
        >
          <ErrorIcon />
        </IconButton>
      );
      break;
    default:
      assertNotReachable(state);
  }
  return (
    // TODO(littlecvr): refactor style attributes, use className if possible.
    <CardText style={{display: 'table-row'}}>
      <div
        style={{
          display: 'table-cell',
          verticalAlign: 'middle',
          padding: 12,
        }}
      >
        {description}
      </div>
      <div
        style={{
          display: 'table-cell',
          textAlign: 'right',
          verticalAlign: 'middle',
        }}
      >
        <IconButton
          tooltip="cancel"
          onClick={cancel}
          iconStyle={{fill: grey700}}
          disabled={!isCancellable(state)}
        >
          <DeleteIcon />
        </IconButton>
        {actionButton}
        <div
          style={{
            display: 'inline-block', width: 48, height: 1, marginRight: 0,
          }}
        />
      </div>
    </CardText>
  );
};

export default Task;
