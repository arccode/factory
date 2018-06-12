// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import {ListItem} from 'material-ui/List';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import * as actions from '../actions';
import ServiceForm from './ServiceForm';

class ServiceList extends React.Component {
  static propTypes = {
    schemata: PropTypes.instanceOf(Immutable.Map).isRequired,
    services: PropTypes.instanceOf(Immutable.Map).isRequired,
    fetchSchemata: PropTypes.func.isRequired,
    fetchServices: PropTypes.func.isRequired,
    updateService: PropTypes.func.isRequired,
  };

  componentDidMount() {
    this.props.fetchServices();
    this.props.fetchSchemata();
  }

  render() {
    const {
      schemata,
      services,
      updateService,
    } = this.props;

    return (
      <div>
        {schemata.keySeq().sort().map((k, i) => {
          const schema = schemata.get(k);
          const service = Immutable.Map({
            // default value for active is same as whether the config contains
            // the key.
            active: services.has(k),
          }).merge(services.get(k, {}));
          return (
            <ListItem
              key={k}
              primaryText={k}
              primaryTogglesNestedList={true}
              nestedItems={[
                <ServiceForm
                  key='form'
                  onSubmit={(values) => updateService(k, values)}
                  form={k}
                  schema={schema}
                  initialValues={service.toJS()}
                  enableReinitialize={true}
                />,
              ]}
            />
          );
        })}
      </div>
    );
  }
}

const mapStateToProps = (state) => {
  return {
    schemata: state.getIn(['service', 'schemata']),
    services: state.getIn(['service', 'services']),
  };
};

const mapDispatchToProps = (dispatch) => {
  return {
    fetchSchemata: () => dispatch(actions.fetchServiceSchemata()),
    fetchServices: () => dispatch(actions.fetchServices()),
    updateService: (name, values) => (
      dispatch(actions.updateService(name, values))
    ),
  };
};

export default connect(mapStateToProps, mapDispatchToProps)(ServiceList);
