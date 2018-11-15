// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Card from '@material-ui/core/Card';
import {
  createStyles,
  Theme,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import React from 'react';
import {connect} from 'react-redux';

import {RootState} from '@app/types';

import {thinScrollBarY} from '@common/styles';
import {DispatchProps} from '@common/types';

import {cancelWaitingTaskAfter, dismissTask} from '../actions';
import {getAllTasks} from '../selectors';

import TaskComponent from './task_component';
import TaskListHeader from './task_list_header';

const styles = (theme: Theme) => createStyles({
  root: {
    display: 'grid',
    gridTemplateColumns: 'minmax(25em, 1fr) 48px 48px 48px',
    alignItems: 'center',
    padding: `0 ${theme.spacing.unit}px`,
  },
  // TODO(pihsun): We should be using CSS subgrid instead when browser support
  // it, since the current implementation relies on having fixed width for
  // button columns, and also make buttons not aligned when there's a
  // scrollbar.
  tasklist: {
    gridColumn: '1 / -1',
    display: 'inherit',
    gridTemplateColumns: 'inherit',
    maxHeight: '70vh',
    ...thinScrollBarY,
  },
});

interface TaskListOwnProps {
  className?: string;
}

type TaskListProps =
  TaskListOwnProps &
  WithStyles<typeof styles> &
  ReturnType<typeof mapStateToProps> &
  DispatchProps<typeof mapDispatchToProps>;

interface TaskListState {
  collapsed: boolean;
}

class TaskList extends React.Component<TaskListProps, TaskListState> {
  state = {
    collapsed: false,
  };

  setCollapsed = (collapsed: boolean) => {
    this.setState({collapsed});
  }

  cancelAllWaitingTasks = () => {
    this.props.cancelWaitingTaskAfter(this.props.tasks[0].taskId);
  }

  dismissAllSucceededTasks = () => {
    for (const {state, taskId} of this.props.tasks) {
      if (state === 'SUCCEEDED') {
        this.props.dismissTask(taskId);
      }
    }
  }

  retryTask = (taskId: string) => {
    console.warn('not implemented yet');
  }

  render() {
    const {
      tasks,
      cancelWaitingTaskAfter,
      dismissTask,
      classes,
      className,
    } = this.props;

    if (tasks.length === 0) {
      return null;
    }

    return (
      <Card className={className}>
        <div className={classes.root}>
          <TaskListHeader
            tasks={tasks}
            cancelAllWaitingTasks={this.cancelAllWaitingTasks}
            dismissAllSucceededTasks={this.dismissAllSucceededTasks}
            collapsed={this.state.collapsed}
            setCollapsed={this.setCollapsed}
          />

          <div className={classes.tasklist}>
            {/* task list */}
            {!this.state.collapsed &&
              tasks.map(({taskId, state, description, progress}) => {
                return (
                  <TaskComponent
                    key={taskId}
                    state={state}
                    description={description}
                    progress={progress}
                    cancel={() => cancelWaitingTaskAfter(taskId)}
                    dismiss={() => dismissTask(taskId)}
                    retry={() => this.retryTask(taskId)}
                  />
                );
              })
            }
          </div>
        </div>
      </Card>
    );
  }
}

const mapStateToProps = (state: RootState) => ({
  tasks: getAllTasks(state),
});

const mapDispatchToProps = {
  cancelWaitingTaskAfter,
  dismissTask,
};

export default connect(mapStateToProps, mapDispatchToProps)(
  withStyles(styles)(TaskList));
