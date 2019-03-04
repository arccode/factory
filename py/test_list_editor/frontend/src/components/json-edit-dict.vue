<template>
  <div class="json-edit-border json-edit-table">
    <template v-for="name in Object.keys(schema.dictSchema)">
      <div class="json-edit-border" :key="'L' + name">
        <v-checkbox
          :disabled="!schema.dictSchema[name].optional"
          :input-value="val.hasOwnProperty(name)"
          :label="name"
          @change="(v) => toggle(name, v)"
        />
      </div>
      <div class="json-edit-border" :key="'R' + name">
        <json-edit
          v-if="val.hasOwnProperty(name)"
          :schema="schema.dictSchema[name].schema"
          :initial="val[name]"
          @change="(v) => onChange(name, v)"
        />
      </div>
    </template>
  </div>
</template>

<script lang="ts">
import {DictFormSchema} from '@/form_utils';
import {isJSONObject, JSONObject, JSONType} from '@/utils';
import {Component, Prop, Vue} from 'vue-property-decorator';

@Component({components: {'json-edit': () => import('./json-edit.vue')}})
export default class JSONEditDict extends Vue {
  @Prop({type: Object, required: true}) schema!: DictFormSchema;
  @Prop({required: true}) initial!: JSONType;

  val: JSONObject = {};

  // Number of unready <json-edit> subcomponents. We should only emit value
  // when all subcomponents are ready, or we might emit values that don't fit
  // the given schema.
  unready = 0;

  created() {
    const src = isJSONObject(this.initial) ? this.initial : {};
    for (const name of Object.keys(this.schema.dictSchema)) {
      if (src.hasOwnProperty(name)) {
        this.val[name] = src[name];
      } else if (!this.schema.dictSchema[name].optional) {
        this.val[name] = null;
      }
    }
    this.unready = Object.keys(this.val).length;
    this.emit();
  }

  emit(): void {
    if (this.unready === 0) this.$emit('change', this.val);
  }

  toggle(name: string, flag: boolean): void {
    if (flag) {
      Vue.set(this.val, name, null);
    } else {
      Vue.delete(this.val, name);
      this.emit();
    }
  }

  onChange(name: string, val: JSONType): void {
    Vue.set(this.val, name, val);
    if (this.unready > 0) this.unready--;
    this.emit();
  }
}
</script>
