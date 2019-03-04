<style>
.json-edit-border {
  border: 1px solid;
  margin: 1px;
}

.json-edit-table {
  display: grid;
  grid-template-columns: max-content 1fr;
}
</style>

<template>
  <component
    :is="getComponentTypeName()"
    :schema="schema"
    :initial="initial"
    @change="onChange"
  />
</template>

<script lang="ts">
import {FormSchema} from '@/form_utils';
import {JSONType} from '@/utils';
import {Component, Prop, Vue} from 'vue-property-decorator';

import JSONEditBasic from './json-edit-basic.vue';
import JSONEditDict from './json-edit-dict.vue';
import JSONEditEnum from './json-edit-enum.vue';
import JSONEditJSON from './json-edit-json.vue';
import JSONEditList from './json-edit-list.vue';

@Component({
  components: {
    'json-edit-basic': JSONEditBasic,
    'json-edit-dict': JSONEditDict,
    'json-edit-enum': JSONEditEnum,
    'json-edit-json': JSONEditJSON,
    'json-edit-list': JSONEditList,
  },
})
export default class JSONEdit extends Vue {
  @Prop({type: Object, required: true}) schema!: FormSchema;
  @Prop({required: true}) initial!: JSONType;

  getComponentTypeName(): string {
    switch (this.schema.type) {
      case 'DICT':
        return 'json-edit-dict';
      case 'ENUM':
        return 'json-edit-enum';
      case 'JSON':
        return 'json-edit-json';
      case 'LIST':
        return 'json-edit-list';
      default:
        return 'json-edit-basic';
    }
  }

  onChange(val: JSONType): void {
    this.$emit('change', val);
  }
}
</script>
