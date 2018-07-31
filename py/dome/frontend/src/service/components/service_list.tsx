// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {ListItem} from 'material-ui/List';
import React from 'react';
import {connect} from 'react-redux';

import {RootState} from '@app/types';

import {fetchServices, fetchServiceSchemata, updateService} from '../actions';
import {getServices, getServiceSchemata} from '../selectors';
import {SchemaMap, Service, ServiceMap} from '../types';

import ServiceForm from './service_form';

interface ServiceListProps {
  schemata: SchemaMap;
  services: ServiceMap;
  fetchServiceSchemata: () => any;
  fetchServices: () => any;
  updateService: (name: string, service: Service) => any;
}

class ServiceList extends React.Component<ServiceListProps> {
  componentDidMount() {
    this.props.fetchServices();
    this.props.fetchServiceSchemata();
  }

  render() {
    const {
      schemata,
      services,
      updateService,
    } = this.props;

    return (
      <div>
        {Object.keys(schemata).sort().map((k, i) => {
          const schema = schemata[k];
          const service = {
            active: services.hasOwnProperty(k),
            ...(services[k] || {}),
          };
          return (
            <ListItem
              key={k}
              primaryText={k}
              primaryTogglesNestedList={true}
              nestedItems={[
                <ServiceForm
                  key="form"
                  onSubmit={(values) => updateService(k, values)}
                  form={k}
                  schema={schema}
                  initialValues={service}
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

const mapStateToProps = (state: RootState) => ({
  schemata: getServiceSchemata(state),
  services: getServices(state),
});

const mapDispatchToProps = {
  fetchServiceSchemata,
  fetchServices,
  updateService,
};

export default connect(mapStateToProps, mapDispatchToProps)(ServiceList);
