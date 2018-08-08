<template>
  <v-app id="inspire">
    <v-toolbar color="indigo" dark fixed app>
      <v-toolbar-title>Application</v-toolbar-title>
    </v-toolbar>
    <v-content>
      <v-container fluid>
        <template v-if="ready">
          <ol>
            <li v-for="dir in fs.dirs" :key="dir.path">
              [{{dir.name}}] {{dir.path}}
              <ul>
                <li v-for="basename in dir.filelist" :key="basename">
                  {{basename}}
                </li>
              </ul>
            </li>
          </ol>
        </template>
      </v-container>
    </v-content>
    <v-footer color="indigo" app>
      <span class="white--text">&copy; 2018</span>
    </v-footer>
  </v-app>
</template>

<script lang="ts">
import Vue from 'vue';
import Component from 'vue-class-component';

import * as common from './common';
import * as rpc from './rpc';

@Component
export default class App extends Vue {
  ready = false;
  fs?: common.FileSystemState;

  async created() {
    this.fs = await rpc.LoadFiles();
    this.ready = true;
  }
}
</script>
