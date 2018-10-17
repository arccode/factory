// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import '@mdi/font/css/materialdesignicons.css';
import 'material-design-icons/iconfont/material-icons.css';
import Vue from 'vue';

import App from './App.vue';
import './plugins/vuetify';

Vue.config.productionTip = false;

new Vue({
  render: (h) => h(App),
}).$mount('#app');
