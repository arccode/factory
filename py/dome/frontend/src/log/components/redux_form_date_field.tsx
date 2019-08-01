// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ReduxFormTextField, {
  ReduxFormTextFieldProps,
} from '@common/components/redux_form_text_field';
import React from 'react';

const ReduxFormDateField = (props: ReduxFormTextFieldProps) => (
  <ReduxFormTextField
    type="date"
    InputLabelProps={{
      shrink: true,
    }}
    {...props}
  />
);

export default ReduxFormDateField;
