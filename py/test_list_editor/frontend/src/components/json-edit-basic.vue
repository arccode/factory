<template>
  <div>
    <template v-if="schema.type === 'BOOL'">
      <v-select solo :items="[false, true]" :value="web" @input="onInput"/>
    </template>
    <template v-else-if="schema.type === 'INT' || schema.type === 'FLOAT'">
      <v-text-field
        solo
        append-icon="mdi-numeric"
        type="number"
        :value="web"
        :rules="[helper.rule]"
        @input="onInput"
      />
    </template>
    <template v-else-if="schema.type === 'STR'">
      <v-text-field
        solo
        append-icon="short_text"
        :value="web"
        @input="onInput"
      />
    </template>
  </div>
</template>

<script lang="ts">
import {BasicFormSchema} from '@/form_utils';
import {JSONType} from '@/utils';
import {Component, Prop, Vue} from 'vue-property-decorator';

interface Helper<ValType, WebType = ValType> {
  init(initial: JSONType): [ValType, WebType];
  parse?(web: WebType): ValType;
  rule?(web: WebType): true | string;
}

const NoneHelper: Helper<null> = {
  init: () => [null, null],
};

const BoolHeaper: Helper<boolean> = {
  init(initial) {
    const v = initial === true;
    return [v, v];
  },
  parse: (web) => web,
};

const IntHelper: Helper<number, string> = {
  init(initial) {
    const v =
        typeof initial === 'number' && Number.isInteger(initial) ? initial : 0;
    return [v, String(v)];
  },
  parse: (web) => Math.trunc(Number(web)),
  rule(web) {
    if (web !== '' && Number.isInteger(Number(web))) return true;
    return 'Please enter an integer.';
  },
};

const FloatHelper: Helper<number, string> = {
  init(initial) {
    const v = typeof initial === 'number' && isFinite(initial) ? initial : 0;
    return [v, String(v)];
  },
  parse: Number,
  rule: (web) => web !== '' ? true : 'Please enter a number.',
};

const StrHelper: Helper<string> = {
  init(initial) {
    const v = typeof initial === 'string' ? initial : '';
    return [v, v];
  },
  parse: (web) => web,
};

@Component
export default class JSONEditBasic extends Vue {
  @Prop({type: Object, required: true}) schema!: BasicFormSchema;
  @Prop({required: true}) initial!: JSONType;

  helper!: Helper<JSONType>;
  val!: JSONType;
  web!: JSONType;

  created() {
    switch (this.schema.type) {
      case 'BOOL':
        this.helper = BoolHeaper;
        break;
      case 'INT':
        this.helper = IntHelper;
        break;
      case 'FLOAT':
        this.helper = FloatHelper;
        break;
      case 'STR':
        this.helper = StrHelper;
        break;
      default:
        this.helper = NoneHelper;
    }
    [this.val, this.web] = this.helper.init(this.initial);
    this.emit();
  }

  emit(): void {
    this.$emit('change', this.val);
  }

  onInput(web: JSONType): void {
    this.val = this.helper.parse!(web);
    this.emit();
  }
}
</script>
