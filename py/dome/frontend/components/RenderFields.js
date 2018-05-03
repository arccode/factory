// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import {fieldPropTypes, fieldArrayPropTypes} from 'redux-form';
import {Field, FieldArray, FormSection} from 'redux-form/immutable';
import Divider from 'material-ui/Divider';
import TextField from 'material-ui/TextField';
import Toggle from 'material-ui/Toggle';
import FloatingActionButton from 'material-ui/FloatingActionButton';
import IconButton from 'material-ui/IconButton';
import ContentClear from 'material-ui/svg-icons/content/clear';
import ContentAdd from 'material-ui/svg-icons/content/add';


const toNumber = value => value && Number(value);
const setFalse = value => value == true || false;

const renderTextField = ({input, label, description, type}) => (
  <TextField
    floatingLabelText={label}
    hintText={description||label}
    type={type}
    {...input}
  />
);

renderTextField.propTypes = {
  label: React.PropTypes.string.isRequired,
  type: React.PropTypes.string.isRequired,
  description: React.PropTypes.string,
  ...fieldPropTypes
};

const renderToggle = ({input, label}) => (
  <Toggle
    label={label}
    labelPosition='right'
    toggled={input.value ? true : false}
    onToggle={input.onChange}
  />
);

renderToggle.propTypes = {
  label: React.PropTypes.string.isRequired,
  ...fieldPropTypes
};

const renderArray = ({fields, schema}) => (
  <div>
    {fields.map((k, i) =>
      <FormSection name={k}>
        <div style={{float: 'right', marginTop: 15 + 'px'}}>
          <IconButton
            tooltip='Remove'
            onClick={() => fields.remove(i)}>
            <ContentClear/>
          </IconButton>
        </div>
        <div style={{marginRight: 50 + 'px'}}>
          <RenderFields
            schema={schema.get('items')}
          />
        </div>
      </FormSection>
    )}
    <div>
      <FloatingActionButton
        mini={true}
        style={{float: 'right', margin: 1 + 'em'}}
        onClick={() => fields.push({})}>
        <ContentAdd />
      </FloatingActionButton>
    </div>
  </div>
);

renderArray.propTypes = {
  schema: React.PropTypes.array.isRequired,
  ...fieldArrayPropTypes
};


var RenderFields = React.createClass({
  propTypes: {
    schema: React.PropTypes.object.isRequired,
  },

  render() {
    const {schema} = this.props;

    const marginStyle = {
      marginLeft: 2 + 'em',
      marginRight: 2 + 'em',
      marginTop: 0.5 + 'em',
      marginBottom: 0.5 + 'em'
    };

    return (
      <div style={marginStyle}>
      {schema.get('properties').keySeq().map((k, i) => {
        var s = schema.getIn(['properties', k]);
        switch(s.get('type')) {
          case 'string':
            return (
              <Field
                name={k}
                component={renderTextField}
                label={k}
                description={s.get('description')}
                type='text'
              />
            );
          case 'integer':
            return (
              <div>
                <Field
                  name={k}
                  component={renderTextField}
                  label={k}
                  description={s.get('description')}
                  normalize={toNumber}
                  type='number'
                />
              </div>
            );
          case 'boolean':
            return (
              <div>
                <Field
                  name={k}
                  component={renderToggle}
                  label={k}
                  normalize={setFalse}
                />
              </div>
            );
          case 'object':
            return (
              <div>
                <FormSection name={k}>
                  <p>{k}</p>
                  <Divider/>
                  <RenderFields
                    schema={s}
                  />
                </FormSection>
              </div>
            );
          case 'array':
            return (
              <div>
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
});

export default RenderFields;
