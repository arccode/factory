<style scoped>
.end {
  grid-column: 1 / 3;
}
</style>

<template>
  <div class="json-edit-border json-edit-table">
    <template v-for="idx in Array.from(val.keys())">
      <div class="json-edit-border" :key="'L' + idx">
        <div>
          <v-btn icon small @click="remove(idx)">
            <v-icon>delete</v-icon>
          </v-btn>
        </div>
        <div>
          <v-btn v-if="idx > 0" icon small @click="swapWithPrevious(idx)">
            <v-icon>arrow_upward</v-icon>
          </v-btn>
        </div>
      </div>
      <div class="json-edit-border" :key="'R' + keys[idx]">
        <json-edit
          :schema="schema.listSchema"
          :initial="val[idx]"
          @change="(v) => onChange(idx, v)"
        />
      </div>
    </template>
    <div class="end">
      <v-btn block flat @click="push">
        <v-icon large>add</v-icon>
      </v-btn>
    </div>
  </div>
</template>

<script lang="ts">
import {ListFormSchema} from '@/form_utils';
import {JSONArray, JSONType} from '@/utils';
import {Component, Prop, Vue} from 'vue-property-decorator';

@Component({components: {'json-edit': () => import('./json-edit.vue')}})
export default class JSONEditList extends Vue {
  @Prop({type: Object, required: true}) schema!: ListFormSchema;
  @Prop({required: true}) initial!: JSONType;

  val: JSONArray = [];

  keys: number[] = [];
  keyCounter = 0;

  // Number of unready <json-edit> subcomponents. We should only emit value
  // when all subcomponents are ready, or we might emit values that don't fit
  // the given schema.
  unready = 0;

  created() {
    if (Array.isArray(this.initial)) {
      this.val = [...this.initial];
      this.val.forEach(this.addKey);
      this.unready = this.val.length;
    }
    this.emit();
  }

  emit(): void {
    if (this.unready === 0) this.$emit('change', this.val);
  }

  addKey(): void {
    this.keys.push(this.keyCounter++);
  }

  push(): void {
    this.val.push(null);
    this.addKey();
  }

  remove(idx: number): void {
    this.val.splice(idx, 1);
    this.keys.splice(idx, 1);
    this.emit();
  }

  swapWithPrevious(idx: number): void {
    this.val.splice(idx - 1, 2, this.val[idx], this.val[idx - 1]);
    this.keys.splice(idx - 1, 2, this.keys[idx], this.keys[idx - 1]);
    this.emit();
  }

  onChange(idx: number, val: JSONType): void {
    this.val[idx] = val;
    if (this.unready > 0) this.unready--;
    this.emit();
  }
}
</script>
