// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Tab from '@material-ui/core/Tab';
import Tabs from '@material-ui/core/Tabs';
import React from 'react';
import {BaseFieldProps, Field, WrappedFieldProps} from 'redux-form';

interface TabNameProps {
  name: string;
  value: string;
}

interface RenderTabsFieldProps {
  tab_types: TabNameProps[];
}

const renderTabsField = ({
  input, tab_types,
}: RenderTabsFieldProps & WrappedFieldProps) => (
  <Tabs
    indicatorColor="primary"
    textColor="primary"
    value={input.value}
    onChange={(event: any, value: number) => input.onChange(value)}
  >
    {tab_types.map((option: TabNameProps) => (
        <Tab label={option.name} value={option.value}/>
    ))}
  </Tabs>
);

type ReduxFormTabsFieldProps =
  RenderTabsFieldProps & BaseFieldProps<RenderTabsFieldProps>;

const ReduxFormTabsField: React.SFC<ReduxFormTabsFieldProps> =
  (props) => (
    <Field {...props} component={renderTabsField} />
  );

export default ReduxFormTabsField;
