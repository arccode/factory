// Copyright 2021 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Card from '@material-ui/core/Card';
import CardContent from '@material-ui/core/CardContent';
import CardHeader from '@material-ui/core/CardHeader';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';
import React from 'react';
import {connect} from 'react-redux';

import project from '@app/project';
import {RootState} from '@app/types';

import {authorizedAxios} from '@common/utils';

type SyncStatusAppProps = ReturnType<typeof mapStateToProps>

function statusToColor(status: any){
  if(status === 'Success') return 'green';
  if(status === 'Failure') return 'red';
  return 'gray';
}

function syncStatusContent(status: any){
  const _items = [];
  for (const [index, value] of Object.entries(status)) {
    _items.push(
      (index === 'status')?
      <TableCell align="left" style={{color: statusToColor(value)}}> {value} </TableCell> :
      <TableCell> {value} </TableCell>
    );
  }
  return _items;
}

class SyncStatusApp extends React.Component<SyncStatusAppProps> {
  timerID: number;
  constructor(props: SyncStatusAppProps, ){
    super(props);
    this.state = {};
    this.timerID = 0;
  }

  getStatus = async() => {
    try {
      const response = await authorizedAxios().get(
        `projects/${this.props.projectName}/sync/status/`
      );
      this.setState(response.data);
    } catch (axiosError) {
      this.setState({});
    }
  }


  renderUpdate = () => {
    const _items = []
    for (const [secondary, status] of Object.entries(this.state)) {
      _items.push(
        <TableRow key={secondary}>
          <TableCell component="th" scope="row">
            {secondary}
          </TableCell>
          {syncStatusContent(status)}
        </TableRow>
       );
    }
    return _items;
  }

  componentDidMount() {
    this.getStatus();
    this.timerID = window.setInterval(this.getStatus, 1000);
  }

  componentWillUnmount() {
    clearInterval(this.timerID);
  }

  render() {
    return (
      <Card>
        <CardHeader title="Sync Status" />
        <CardContent>
        <Table aria-label="simple table">
          <TableHead>
            <TableRow>
              <TableCell>Secondary Umpire URL</TableCell>
              <TableCell>Sync Status</TableCell>
              <TableCell>Last Timestamp</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {this.renderUpdate()}
          </TableBody>
        </Table>
        </CardContent>
      </Card>
    )
  }
}

const mapStateToProps = (state: RootState) => ({
  projectName: project.selectors.getCurrentProject(state),
});

export default connect(mapStateToProps, {})(SyncStatusApp);;