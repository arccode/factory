// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import React from 'react';
import {Card, CardTitle, CardText} from 'material-ui/Card';

import ResourceTable from './ResourceTable';

var Bundle = React.createClass({
  propTypes: {
    bundle: React.PropTypes.instanceOf(Immutable.Map).isRequired
  },

  render: function() {
    const {bundle} = this.props;

    return (
      <Card className="bundle">
        <CardTitle title={bundle.get('name')} subtitle={bundle.get('note')} />
        <CardText>
          <ResourceTable bundle={bundle} />
        </CardText>
      </Card>
    );
  }
});

export default Bundle;
