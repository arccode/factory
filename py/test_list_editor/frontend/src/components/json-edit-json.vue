<template>
  <v-textarea solo :value="web" :rules="[rule]" @input="onInput"/>
</template>

<script lang="ts">
import {JSONFormSchema} from '@/form_utils';
import {isJSONObject, JSONType, prettyJSON} from '@/utils';
import {Component, Prop, Vue} from 'vue-property-decorator';

const check =
    (schema: JSONFormSchema, val: JSONType): [JSONType, true | string] => {
  switch (schema.jsonSchema) {
    case 'LIST':
      if (!Array.isArray(val)) return [[], 'Must be a JSON array.'];
      break;
    case 'DICT':
      if (!isJSONObject(val)) return [{}, 'Must be a JSON object.'];
      break;
    default:
      break;
  }
  return [val, true];
};

@Component
export default class JSONEditJSON extends Vue {
  @Prop({type: Object, required: true}) schema!: JSONFormSchema;
  @Prop({required: true}) initial!: JSONType;

  val!: JSONType;
  web!: string;

  created() {
    this.val = check(this.schema, this.initial)[0];
    this.web = prettyJSON(this.val);
    this.emit();
  }

  emit(): void {
    this.$emit('change', this.val);
  }

  rule(web: string): true | string {
    let v: JSONType;
    try {
      v = JSON.parse(web);
    } catch (err) {
      return (err as Error).message;
    }
    return check(this.schema, v)[1];
  }

  onInput(web: string): void {
    let v: JSONType = null;
    try {
      v = JSON.parse(web);
    } catch (err) {
      // `v` will fall back to the default value in the following check.
    }
    this.val = check(this.schema, v)[0];
    this.emit();
  }
}
</script>
