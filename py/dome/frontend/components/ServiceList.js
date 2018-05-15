// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {connect} from 'react-redux';
import Immutable from 'immutable';
import React from 'react';
import {ListItem} from 'material-ui/List';

import ServicesActions from '../actions/servicesactions';
import ServiceForm from './ServiceForm';

var ServiceList = React.createClass({
  propTypes: {
    schemata: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    services: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    fetchSchemata: React.PropTypes.func.isRequired,
    fetchServices: React.PropTypes.func.isRequired,
    updateService: React.PropTypes.func.isRequired
  },

  componentDidMount() {
    this.props.fetchServices();
    this.props.fetchSchemata();
  },

  render() {
    const {
      schemata,
      services,
      updateService
    } = this.props;

    return (
      <div>
        {schemata.keySeq().sort().map((k, i) => {
          var schema = schemata.get(k);
          var service = Immutable.Map({});
          if(services.has(k)) {
            service = services.get(k);
            if(!service.has('active'))
              service = service.set('active', true);
          }
          return (
            <ListItem
              key={k}
              primaryText={k}
              primaryTogglesNestedList={true}
              nestedItems={[
                <ServiceForm
                  key='form'
                  onSubmit={values => updateService(k, values)}
                  form={k}
                  schema={schema}
                  initialValues={service.toJS()}
                  enableReinitialize={true}
                />
              ]}
            />
          );
        })}
      </div>
    );
  }
});

function mapStateToProps(state) {
  return {
    schemata: state.getIn(['service', 'schemata']),
    services: state.getIn(['service', 'services'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    fetchSchemata: () => dispatch(ServicesActions.fetchServiceSchemata()),
    fetchServices: () => dispatch(ServicesActions.fetchServices()),
    updateService: (name, values) => {
      dispatch(ServicesActions.updateService(name, values));
    }
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(ServiceList);
