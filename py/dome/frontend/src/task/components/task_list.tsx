// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardActions, CardHeader} from 'material-ui/Card';
import IconButton from 'material-ui/IconButton';
import {grey700} from 'material-ui/styles/colors';
import DismissIcon from 'material-ui/svg-icons/action/check-circle';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import CollapseIcon from 'material-ui/svg-icons/navigation/expand-less';
import ExpandIcon from 'material-ui/svg-icons/navigation/expand-more';
import React from 'react';
import {connect} from 'react-redux';

import {RootState} from '@app/types';

import {cancelWaitingTaskAfter, dismissTask} from '../actions';
import {isCancellable, isRunning} from '../constants';
import {getAllTasks} from '../selectors';
import {Task, TaskState} from '../types';

import TaskComponent from './task_component';

interface TaskListProps {
  tasks: Task[];
  cancelWaitingTaskAfter: (taskID: string) => any;
  dismissTask: (taskID: string) => any;
}

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
    this.props.cancelWaitingTaskAfter(this.props.tasks[0].taskID);
  }

  dismissAllSucceededTasks = () => {
    for (const {state, taskID} of this.props.tasks) {
      if (state === 'SUCCEEDED') {
        this.props.dismissTask(taskID);
      }
    }
  }

  retryTask = (taskID: string) => {
    console.warn('not implemented yet');
  }

  render() {
    const {tasks, cancelWaitingTaskAfter, dismissTask} = this.props;

    if (tasks.length === 0) {
      return null;
    }

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
      <Card
        containerStyle={{display: 'table'}}
      >
        {/* title bar */}
        <div
          style={{display: 'table-row'}}
        >
          <CardHeader
            title="Tasks"
            subtitle={taskSummary}
            style={{
              display: 'table-cell',
              verticalAlign: 'middle',
              padding: 12,
            }}
          />
          <CardActions
            style={{
              display: 'table-cell',
              textAlign: 'right',
              verticalAlign: 'middle',
              padding: 0,
            }}
          >
            {!this.state.collapsed &&
              <>
                <IconButton
                  tooltip="cancel all waiting tasks"
                  onClick={this.cancelAllWaitingTasks}
                  style={{marginRight: 0}}
                  iconStyle={{fill: grey700}}
                  disabled={!hasCancellableTask}
                >
                  <DeleteIcon />
                </IconButton>
                <IconButton
                  tooltip="dismiss all finished tasks"
                  onClick={this.dismissAllSucceededTasks}
                  style={{marginRight: 0}}
                  iconStyle={{fill: 'green'}}
                >
                  <DismissIcon />
                </IconButton>
                <IconButton
                  tooltip="collapse"
                  style={{marginRight: 0}}
                  onClick={() => this.setCollapsed(true)}
                >
                  <CollapseIcon />
                </IconButton>
              </>
            }
            {this.state.collapsed &&
              <>
                {/* two padding blank icons */}
                <div
                  style={{
                    display: 'inline-block',
                    width: 48,
                    height: 1,
                    marginRight: 0,
                  }}
                />
                <div
                  style={{
                    display: 'inline-block',
                    width: 48,
                    height: 1,
                    marginRight: 0,
                  }}
                />
                <IconButton
                  tooltip="expand"
                  style={{marginRight: 0}}
                  onClick={() => this.setCollapsed(false)}
                >
                  <ExpandIcon />
                </IconButton>
              </>
            }
          </CardActions>
        </div>

        {/* task list */}
        {!this.state.collapsed &&
          tasks.map(({taskID, state, description, progress}) => {
            return (
              <TaskComponent
                key={taskID}
                state={state}
                description={description}
                progress={progress}
                cancel={() => cancelWaitingTaskAfter(taskID)}
                dismiss={() => dismissTask(taskID)}
                retry={() => this.retryTask(taskID)}
              />
            );
          })}
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

export default connect(mapStateToProps, mapDispatchToProps)(TaskList);
