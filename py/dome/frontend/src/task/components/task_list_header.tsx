// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import IconButton from '@material-ui/core/IconButton';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import Tooltip from '@material-ui/core/Tooltip';
import Typography from '@material-ui/core/Typography';
import DismissIcon from '@material-ui/icons/CheckCircle';
import DeleteIcon from '@material-ui/icons/Delete';
import CollapseIcon from '@material-ui/icons/ExpandLess';
import ExpandIcon from '@material-ui/icons/ExpandMore';
import React from 'react';

import {isCancellable, isRunning} from '../constants';
import {Task, TaskState} from '../types';

import {styles as taskComponentStyles} from './task_component';

const styles = (theme: Theme) => createStyles({
  ...taskComponentStyles(theme),
});

interface TaskListHeaderProps extends WithStyles<typeof styles> {
  tasks: Task[];
  cancelAllWaitingTasks: () => void;
  dismissAllSucceededTasks: () => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
}

const TaskListHeader: React.SFC<TaskListHeaderProps> = ({
  tasks,
  cancelAllWaitingTasks,
  dismissAllSucceededTasks,
  collapsed,
  setCollapsed,
  classes,
}) => {
  const counts = tasks.reduce((groups, {state}) => {
    groups[state] = (groups[state] || 0) + 1;
    return groups;
  }, {} as {[state in TaskState]?: number});
  const running = tasks.filter(({state}) => isRunning(state)).length;
  const hasCancellableTask = tasks.some(({state}) => isCancellable(state));

  const taskSummary = `${counts.WAITING || 0} waiting, ` +
    `${running} running, ` +
    `${counts.SUCCEEDED || 0} succeeded, ` +
    `${counts.FAILED || 0} failed`;

  return (
    <>
      <div className={classes.description}>
        <Typography variant="subheading">Tasks</Typography>
        <Typography variant="caption" color="textSecondary">
          {taskSummary}
        </Typography>
      </div>
      {collapsed ? (
        <>
          {/* two padding blank icons */}
          <div />
          <div />
          <IconButton onClick={() => setCollapsed(false)}>
            <ExpandIcon />
          </IconButton>
        </>
      ) : (
        <>
          <Tooltip title="cancel all waiting tasks">
            <div>
              {/* We need an extra div so tooltip works when button is disabled.
                */}
              <IconButton
                onClick={cancelAllWaitingTasks}
                disabled={!hasCancellableTask}
              >
                <DeleteIcon />
              </IconButton>
            </div>
          </Tooltip>
          <Tooltip title="dismiss all finished tasks">
            <IconButton onClick={dismissAllSucceededTasks}>
              <DismissIcon
                color="action"
                classes={{
                  colorAction: classes.colorAction,
                }}
              />
            </IconButton>
          </Tooltip>
          <IconButton onClick={() => setCollapsed(true)}>
            <CollapseIcon />
          </IconButton>
        </>
      )}
    </>
  );
};

export default withStyles(styles)(TaskListHeader);
