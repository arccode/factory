// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Divider from '@material-ui/core/Divider';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import IconButton from '@material-ui/core/IconButton';
import {
  createStyles,
  WithStyles,
  withStyles,
} from '@material-ui/core/styles';
import Switch from '@material-ui/core/Switch';
import Tooltip from '@material-ui/core/Tooltip';
import AddIcon from '@material-ui/icons/Add';
import ClearIcon from '@material-ui/icons/Clear';
import React from 'react';
import {
  Field,
  FieldArray,
  FormSection,
  WrappedFieldArrayProps,
  WrappedFieldProps,
} from 'redux-form';

import ReduxFormTextField from '@common/components/redux_form_text_field';
import {parseNumber} from '@common/form';

import {Schema} from '../types';

interface RenderSwitchProps {
  label: string;
}

const renderSwitch =
  ({input, label}: RenderSwitchProps & WrappedFieldProps) => (
    <FormControlLabel
      control={
        <Switch
          color="primary"
          checked={input.value}
          onChange={input.onChange}
        />
      }
      label={label}
    />
  );

interface RenderArrayProps {
  objectKey: string;
  schema: Schema;
}

const arrayStyles = createStyles({
  itemRow: {
    display: 'flex',
  },
  itemContent: {
    flex: 1,
  },
});

type WrappedRenderArrayProps =
  RenderArrayProps
    & WrappedFieldArrayProps<any>
    & WithStyles<typeof arrayStyles>;

const renderArray = withStyles(arrayStyles)(
  ({objectKey, fields, schema, classes}: WrappedRenderArrayProps) => (
    <div>
      <div className={classes.itemRow}>
        <p className={classes.itemContent}>{objectKey}</p>
        <Tooltip title="Add">
          <IconButton onClick={() => fields.push({})}>
            <AddIcon />
          </IconButton>
        </Tooltip>
      </div>
      <Divider />
      {fields.map((k, i) => (
        <FormSection name={k} key={k}>
          {i > 0 && <Divider />}
          <div className={classes.itemRow}>
            <RenderFields schema={schema.items as Schema} />
            <Tooltip title="Remove">
              <IconButton onClick={() => fields.remove(i)}>
                <ClearIcon />
              </IconButton>
            </Tooltip>
          </div>
        </FormSection>
      ))}
    </div>
  ),
);

const styles = createStyles({
  field: {
    margin: '0 2em',
  },
});

interface RenderFieldsProps {
  schema: Schema;
}

const RenderFields = withStyles(styles)(
  ({schema, classes}: RenderFieldsProps & WithStyles<typeof styles>) => {
    const properties = schema.properties as {[k: string]: Schema};

    const renderField = (k: string, value: Schema): React.ReactNode => {
      switch (value.type) {
        case 'string':
          return (
            <ReduxFormTextField
              key={k}
              name={k}
              label={k}
              placeholder={value.description}
              margin="dense"
            />
          );
        case 'integer':
          return (
            <ReduxFormTextField
              key={k}
              name={k}
              label={k}
              placeholder={value.description}
              parse={parseNumber}
              type="number"
              margin="dense"
            />
          );
        case 'boolean':
          return (
            <Field
              key={k}
              name={k}
              component={renderSwitch}
              label={k}
            />
          );
        case 'object':
          return (
            <FormSection name={k} key={k}>
              <p>{k}</p>
              <Divider />
              <RenderFields schema={value} />
            </FormSection>
          );
        case 'array': {
          // The "as any" is to get around redux-form typing bug as in
          // https://github.com/DefinitelyTyped/DefinitelyTyped/issues/23592.
          return (
            <div key={k}>
              <FieldArray
                name={k}
                objectKey={k}
                schema={value}
                component={renderArray as any}
              />
            </div>
          );
        }
        default:
          return null;
      }
    };

    return (
      <div className={classes.field}>
        {Object.entries(properties).map(([k, v]) => renderField(k, v))}
      </div>
    );
  });

export default RenderFields;
