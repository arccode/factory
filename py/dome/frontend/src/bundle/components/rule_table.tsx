// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import grey from '@material-ui/core/colors/grey';
import {
  createStyles,
  Theme,
  withStyles,
  WithStyles,
} from '@material-ui/core/styles';
import produce from 'immer';
import ChipInput from 'material-ui-chip-input';
import React from 'react';

import {RuleKey, Rules} from '../types';

const styles = (theme: Theme) => createStyles({
  root: {
    display: 'grid',
    gridTemplateColumns: '1fr 2fr',
    width: '100%',
  },
  cell: {
    padding: theme.spacing.unit,
    display: 'flex',
    alignItems: 'center',
    borderBottom: `1px solid ${grey[300]}`,
    fontSize: theme.typography.pxToRem(13),
  },
});

interface RuleTableProps extends WithStyles<typeof styles> {
  rules: Partial<Rules>;
  changeRules: (rules: Partial<Rules>) => void;
}

class RuleTable extends React.Component<RuleTableProps> {
  handleAdd = (key: RuleKey, value: string) => {
    const rules = produce(this.props.rules, (draft) => {
      draft[key] = [...(draft[key] || []), value];
    });
    this.props.changeRules(rules);
  }

  handleDelete = (key: RuleKey, value: string) => {
    const rules = produce(this.props.rules, (draft) => {
      const values = draft[key];
      if (!values) return;
      const index = values.indexOf(value);
      if (index >= 0) {
        values.splice(index, 1);
      }
    });
    this.props.changeRules(rules);
  }

  render() {
    const {rules, classes} = this.props;

    return (
      <div className={classes.root}>
        <div className={classes.cell}>MAC</div>
        <div className={classes.cell}>
          <ChipInput
            value={rules.macs || []}
            onAdd={(m) => this.handleAdd('macs', m)}
            onDelete={(m) => this.handleDelete('macs', m)}
          />
        </div>
        <div className={classes.cell}>SN</div>
        <div className={classes.cell}>
          <ChipInput
            value={rules.serialNumbers || []}
            onAdd={(s) => this.handleAdd('serialNumbers', s)}
            onDelete={(s) => this.handleDelete('serialNumbers', s)}
          />
        </div>
        <div className={classes.cell}>MLB SN</div>
        <div className={classes.cell}>
          <ChipInput
            value={rules.mlbSerialNumbers || []}
            onAdd={(s) => this.handleAdd('mlbSerialNumbers', s)}
            onDelete={(s) => this.handleDelete('mlbSerialNumbers', s)}
          />
        </div>
      </div>
    );
  }
}

export default withStyles(styles)(RuleTable);
