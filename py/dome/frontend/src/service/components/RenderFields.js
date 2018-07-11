// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Divider from 'material-ui/Divider';
import FloatingActionButton from 'material-ui/FloatingActionButton';
import IconButton from 'material-ui/IconButton';
import ContentAdd from 'material-ui/svg-icons/content/add';
import ContentClear from 'material-ui/svg-icons/content/clear';
import Toggle from 'material-ui/Toggle';
import PropTypes from 'prop-types';
import React from 'react';
import {
  Field,
  FieldArray,
  fieldArrayPropTypes,
  fieldPropTypes,
  FormSection,
} from 'redux-form';

import {renderTextField} from '@common/form';

const toNumber = (value) => value && Number(value);

const renderToggle = ({input, label}) => (
  <Toggle
    label={label}
    labelPosition="right"
    toggled={input.value}
    onToggle={input.onChange}
  />
);

renderToggle.propTypes = {
  label: PropTypes.string.isRequired,
  ...fieldPropTypes,
};

const renderArray = ({fields, schema}) => (
  <div>
    {fields.map((k, i) =>
      <FormSection name={k} key={k}>
        <div style={{float: 'right', marginTop: '15px'}}>
          <IconButton
            tooltip="Remove"
            onClick={() => fields.remove(i)}>
            <ContentClear/>
          </IconButton>
        </div>
        <div style={{marginRight: '50px'}}>
          <RenderFields
            schema={schema.items}
          />
        </div>
      </FormSection>,
    )}
    <div>
      <FloatingActionButton
        mini={true}
        style={{float: 'right', margin: '1em'}}
        onClick={() => fields.push({})}>
        <ContentAdd />
      </FloatingActionButton>
    </div>
  </div>
);

renderArray.propTypes = {
  schema: PropTypes.object.isRequired,
  ...fieldArrayPropTypes,
};

class RenderFields extends React.Component {
  static propTypes = {
    schema: PropTypes.object.isRequired,
  };

  render() {
    const {schema} = this.props;

    const marginStyle = {
      marginLeft: '2em',
      marginRight: '2em',
      marginTop: '0.5em',
      marginBottom: '0.5em',
    };

    return (
      <div style={marginStyle}>
        {Object.keys(schema.properties).map((k, i) => {
          const s = schema.properties[k];
          switch (s.type) {
            case 'string':
              return (
                <Field
                  key={k}
                  name={k}
                  component={renderTextField}
                  label={k}
                  description={s.description}
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
                  description={s.description}
                  normalize={toNumber}
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
                  <Divider/>
                  <RenderFields
                    schema={s}
                  />
                </FormSection>
              );
            case 'array':
              return (
                <div key={k}>
                  <p>{k}</p>
                  <Divider/>
                  <FieldArray
                    name={k}
                    schema={s}
                    component={renderArray}
                  />
                </div>
              );
            default:
              break;
          }
        })}
      </div>
    );
  }
}

export default RenderFields;
