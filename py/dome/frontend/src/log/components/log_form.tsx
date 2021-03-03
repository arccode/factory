// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import Card from '@material-ui/core/Card';
import CardActions from '@material-ui/core/CardActions';
import CardContent from '@material-ui/core/CardContent';
import List from '@material-ui/core/List';
import ListItem from '@material-ui/core/ListItem';
import ListSubheader from '@material-ui/core/ListSubheader';
import MenuItem from '@material-ui/core/MenuItem';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import React from 'react';
import {connect} from 'react-redux';
import {
  FormErrors,
  formValueSelector,
  InjectedFormProps,
  reduxForm,
} from 'redux-form';

import {RootState} from '@app/types';
import ReduxFormTextField from '@common/components/redux_form_text_field';

import {getDefaultDownloadDate} from '../selectors';
import {LogFormData} from '../types';

import ReduxFormDateField from './redux_form_date_field';
import ReduxFormTabsField from './redux_form_tabs_field';

const units = ['MB', 'GB'];

const logTypes = [
  {name: 'log', value: 'log'},
  {name: 'report', value: 'report'},
  {name: 'csv (echo code inside)', value: 'csv'},
];

interface LogFormOwnProps {
  logType: string;
}

const styles = (theme: Theme) => createStyles({
  root: {
    marginBottom: theme.spacing.unit * 4,
  },
});

type LogFormProps =
  WithStyles<typeof styles> &
  LogFormOwnProps &
  ReturnType<typeof mapStateToProps>;

const validate = (values: LogFormData, props: LogFormProps) => {
  const errors: FormErrors<LogFormData> = {};
  const {
    archiveSize,
    startDate,
    endDate,
  } = values;

  if (startDate > endDate) {
    errors.startDate = 'start date must be before end date';
    errors.endDate = 'start date must be before end date';
  }

  if (!archiveSize) {
    errors.archiveSize = 'required';
  } else if (archiveSize <= 0) {
    errors.archiveSize = 'archive size must be larger than 0';
  }

  return errors;
};

class LogForm extends React.Component<
  LogFormProps
  & InjectedFormProps<LogFormData, LogFormProps>> {
  render() {
    const {
      handleSubmit,
      logType,
      classes,
    } = this.props;

    return (
      <form onSubmit={handleSubmit}>
        <Card className={classes.root}>
          <CardContent>
            <ReduxFormTabsField
              name="logType"
              tab_types={logTypes}
            />
          </CardContent>
          {(logType === 'csv') ||
            <CardContent>
              <List>
                <ListSubheader>Maximum Archive Size</ListSubheader>
                <ListItem>
                  <ReduxFormTextField
                    name="archiveSize"
                    label="size"
                    type="number"
                  />
                  <ReduxFormTextField
                    name="archiveUnit"
                    label="unit"
                    select
                  >
                    {units.map((option) => (
                      <MenuItem key={option} value={option}>
                        {option}
                      </MenuItem>
                    ))}
                  </ReduxFormTextField>
                </ListItem>
                <ListSubheader>Dates</ListSubheader>
                <ListItem>
                  <ReduxFormDateField
                    name="startDate"
                    label="start date"
                    ignoreTouch
                  />
                  <ReduxFormDateField
                    name="endDate"
                    label="end date"
                    ignoreTouch
                  />
                </ListItem>
              </List>
            </CardContent>}
          <CardActions>
            <Button type="submit" color="primary">
              Download
            </Button>
          </CardActions>
        </Card>
      </form>
    );
  }
}

const selector = formValueSelector('logForm');

const mapStateToProps = (state: RootState) => ({
  logType: selector(state, 'logType'),
  initialValues: {
    logType: 'log',
    archiveSize: 200,
    archiveUnit: 'MB',
    startDate: getDefaultDownloadDate(state),
    endDate: getDefaultDownloadDate(state),
  },
});

export default withStyles(styles)(connect(mapStateToProps)(
  reduxForm<LogFormData, LogFormProps>({
    form: 'logForm',
    validate,
    enableReinitialize: true,
})(LogForm)));
