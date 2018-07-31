// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Divider from 'material-ui/Divider';
import FloatingActionButton from 'material-ui/FloatingActionButton';
import IconButton from 'material-ui/IconButton';
import ContentAdd from 'material-ui/svg-icons/content/add';
import ContentClear from 'material-ui/svg-icons/content/clear';
import Toggle from 'material-ui/Toggle';
import React from 'react';
import {
  Field,
  FieldArray,
  FormSection,
  WrappedFieldArrayProps,
  WrappedFieldProps,
} from 'redux-form';

import {parseNumber, renderTextField} from '@common/form';

import {Schema} from '../types';

interface RenderToggleProps extends WrappedFieldProps {
  label: string;
}

const renderToggle = ({input, label}: RenderToggleProps) => (
  <Toggle
    label={label}
    labelPosition="right"
    toggled={input.value}
    onToggle={input.onChange}
  />
);

interface RenderArrayProps {
  schema: Schema;
}

type WrappedRenderArrayProps = RenderArrayProps & WrappedFieldArrayProps<any>;

const renderArray: React.SFC<WrappedRenderArrayProps> = ({fields, schema}) => (
  <div>
    {fields.map((k, i) =>
      <FormSection name={k} key={k}>
        <div style={{float: 'right', marginTop: '15px'}}>
          <IconButton
            tooltip="Remove"
            onClick={() => fields.remove(i)}
          >
            <ContentClear />
          </IconButton>
        </div>
        <div style={{marginRight: '50px'}}>
          <RenderFields
            schema={schema.items as Schema}
          />
        </div>
      </FormSection>,
    )}
    <div>
      <FloatingActionButton
        mini={true}
        style={{float: 'right', margin: '1em'}}
        onClick={() => fields.push({})}
      >
        <ContentAdd />
      </FloatingActionButton>
    </div>
  </div>
);

interface RenderFieldsProps {
  schema: Schema;
}

class RenderFields extends React.Component<RenderFieldsProps> {
  render(): React.ReactNode {
    const {schema} = this.props;

    const marginStyle = {
      marginLeft: '2em',
      marginRight: '2em',
      marginTop: '0.5em',
      marginBottom: '0.5em',
    };

    const properties = schema.properties as {[k: string]: Schema};

    const renderField = (k: string, value: Schema): React.ReactNode => {
      switch (value.type) {
        case 'string':
          return (
            <Field
              key={k}
              name={k}
              component={renderTextField}
              label={k}
              hintText={value.description}
              type="text"
            />
          );
        case 'integer':
          return (
            <Field
              key={k}
              name={k}
              component={renderTextField}
              label={k}
              hintText={value.description}
              parse={parseNumber}
              type="number"
            />
          );
        case 'boolean':
          return (
            <Field
              key={k}
              name={k}
              component={renderToggle}
              label={k}
            />
          );
        case 'object':
          return (
            <FormSection name={k} key={k}>
              <p>{k}</p>
              <Divider />
              <RenderFields
                schema={value}
              />
            </FormSection>
          );
        case 'array': {
          // The "as any" is to get around redux-form typing bug as in
          // https://github.com/DefinitelyTyped/DefinitelyTyped/issues/23592.
          return (
            <div key={k}>
              <p>{k}</p>
              <Divider />
              <FieldArray
                name={k}
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
      <div style={marginStyle}>
        {Object.entries(properties).map(([k, v]) => renderField(k, v))}
      </div>
    );
  }
}

export default RenderFields;
