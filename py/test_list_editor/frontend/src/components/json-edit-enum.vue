<template>
  <v-select solo :items="schema.enumSchema" :value="val" @input="onInput"/>
</template>

<script lang="ts">
import {EnumFormSchema} from '@/form_utils';
import {JSONType} from '@/utils';
import {Component, Prop, Vue} from 'vue-property-decorator';

@Component
export default class JSONEditEnum extends Vue {
  @Prop({type: Object, required: true}) schema!: EnumFormSchema;
  @Prop({required: true}) initial!: JSONType;

  val = '';

  created() {
    if (typeof this.initial === 'string' &&
        this.schema.enumSchema.includes(this.initial)) {
      this.val = this.initial;
    } else if (this.schema.enumSchema.length > 0) {
      this.val = this.schema.enumSchema[0];
    }
    this.emit();
  }

  emit(): void {
    this.$emit('change', this.val);
  }

  onInput(web: string): void {
    this.val = web;
    this.emit();
  }
}
</script>
