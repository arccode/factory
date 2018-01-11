// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('_');
goog.provide('cros.factory.i18n');

goog.require('goog.dom');
goog.require('goog.html.SafeHtml');

goog.scope(() => {

const ns = cros.factory.i18n;

/**
 * @typedef {function(!Object<string, string>): string}
 */
ns.FormatFunc;

/**
 * Type that most i18n functions return.
 * @typedef {!Object<string, string>}
 */
ns.TranslationDict;

/**
 * The cache for format strings.
 * @type {!Object<string, !cros.factory.i18n.FormatFunc>}
 * @private
 */
ns.formatCache_ = Object.create(null);

/**
 * Default locale to use when no translation found.
 * @type {string}
 * @const
 */
ns.DEFAULT_LOCALE = 'en-US';

/**
 * All support locales.
 * @type {!Array<string>}
 */
ns.locales = [ns.DEFAULT_LOCALE];

/**
 * Dictionary that contains all translations.
 * @type {!Object<string, !cros.factory.i18n.TranslationDict>}
 * @private
 */
ns.translations_ = Object.create(null);

/**
 * Initialize locales and translations.
 *
 * The window['goofy_i18n_data'] is set in goofy-translations.js.
 */
ns.initI18nData = () => {
  const globalI18nData =
      /**
       * @type {{locales: !Array<string>,
       * translations: !Array<!cros.factory.i18n.TranslationDict>}}
       */
      (window['goofy_i18n_data']);

  if (globalI18nData) {
    ns.locales = globalI18nData['locales'];
    for (const text of globalI18nData['translations']) {
      const key = text[ns.DEFAULT_LOCALE];
      ns.translations_[key] = text;
    }
  }
};

ns.initI18nData();

/**
 * Parse the format string and return the function for formatting.
 * This function emulates what python str.format() does.
 * @param {string} format the format string.
 * @return {!cros.factory.i18n.FormatFunc}
 * @private
 */
ns.stringFormatImpl_ = (format) => {
  const /** !Array<string> */ strs = [''];
  const /** !Array<string> */ vars = [];
  let i = 0;
  while (i < format.length) {
    if (format.charAt(i) == '{') {
      if (i + 1 < format.length && format[i + 1] == '{') {
        strs[strs.length - 1] += format.charAt(i);
        i += 2;
      } else {
        let var_name = '';
        i++;
        while (i < format.length && format.charAt(i) != '}') {
          var_name += format.charAt(i);
          i++;
        }
        if (i == format.length) {
          throw new Error('Unclosed {.');
        }
        vars.push(var_name);
        strs.push('');
        i++;
      }
    } else if (format.charAt(i) == '}') {
      if (i + 1 == format.length || format[i + 1] != '}') {
        throw new Error('} should be escaped by }}.');
      }
      strs[strs.length - 1] += format.charAt(i);
      i += 2;
    } else {
      strs[strs.length - 1] += format.charAt(i);
      i++;
    }
  }
  return (
      /** @return {string} */ function(/** !Object<string, string> */ dict) {
        let ret = strs[0];
        for (let i = 0; i < vars.length; i++) {
          ret += dict[vars[i]];
          ret += strs[i + 1];
        }
        return ret;
      });
};

/**
 * Cached version for cros.factory.i18n.stringFormatImpl_.
 * @param {string} format the format string.
 * @return {!cros.factory.i18n.FormatFunc}
 * @private
 */
ns.stringFormatCached_ = (format) => {
  if (!(format in cros.factory.i18n.formatCache_)) {
    cros.factory.i18n.formatCache_[format] =
        cros.factory.i18n.stringFormatImpl_(format);
  }
  return cros.factory.i18n.formatCache_[format];
};

/**
 * Most of the following functions have same signatures with the corresponding
 * methods in python module cros.factory.test.i18n.*.
 * See document there for more detailed explanation.
 */

/**
 * Returns a text untranslated for all locales.
 * @param {string} text
 * @return {!cros.factory.i18n.TranslationDict}
 */
ns.noTranslation = (text) => {
  const ret = Object.create(null);
  for (const locale of ns.locales) {
    ret[locale] = text;
  }
  return ret;
};

/**
 * Returns a text translated.
 * @param {string} text the text to be translated.
 * @return {!cros.factory.i18n.TranslationDict}
 */
ns.translation = (text) => {
  if (text in ns.translations_) {
    return ns.translations_[text];
  } else {
    return ns.noTranslation(text);
  }
};

/**
 * Make sure the input is a TranslationDict, pass it to translation or
 * noTranslation if it isn't, based on the value of argument translate.
 * @param {string|!cros.factory.i18n.TranslationDict} obj
 * @param {boolean=} translate whether string should be passed to translation
 *     or noTranslation.
 * @return {!cros.factory.i18n.TranslationDict}
 */
ns.translated = (obj, translate = true) => {
  // Because of type checking for dict object is MUCH harder in JavaScript,
  // we assume that passed in obj is a TranslationDict if it's an object.
  if (typeof obj === 'object') {
    const ret = Object.create(null);
    for (const locale of ns.locales) {
      ret[locale] = (locale in obj) ? obj[locale] : obj[ns.DEFAULT_LOCALE];
    }
    return ret;
  } else {
    return translate ? ns.translation(obj) : ns.noTranslation(obj);
  }
};

/**
 * Do python-like i18n string format.
 * @param {string|!cros.factory.i18n.TranslationDict} format the format
 *     string.
 * @param {!Object<string, string>} dict the arguments in format string.
 * @return {!cros.factory.i18n.TranslationDict}
 */
ns.stringFormat = (format, dict) => {
  const format_dict = ns.translated(format);
  if (Object.keys(dict).length === 0) {
    // Don't run stringFormatCached_ when there's no arguments, to avoid
    // putting all translated strings into the cache.
    return format_dict;
  }
  const translated_dict = Object.create(null);
  for (const key of Object.keys(dict)) {
    translated_dict[key] = ns.translated(dict[key], false);
  }
  const ret = Object.create(null);
  for (const locale of ns.locales) {
    const args = Object.create(null);
    for (const key of Object.keys(translated_dict)) {
      args[key] = translated_dict[key][locale];
    }
    ret[locale] = ns.stringFormatCached_(format_dict[locale])(args);
  }
  return ret;
};

/**
 * Make a translated label.
 * @param {string|!cros.factory.i18n.TranslationDict} text
 * @return {!goog.html.SafeHtml}
 */
ns.i18nLabel = (text) => {
  const label = ns.translated(text);
  const children = [];
  for (const locale of ns.locales) {
    const translated_label = label[locale];
    const html_class = `goofy-label-${locale}`;
    children.push(goog.html.SafeHtml.create(
        'span', {class: html_class},
        goog.html.SafeHtml.htmlEscapePreservingNewlines(translated_label)));
  }
  return goog.html.SafeHtml.concat(children);
};

/**
 * Make a translated label as DOM node.
 * @param {string|!cros.factory.i18n.TranslationDict} text
 * @return {!Node}
 */
ns.i18nLabelNode = (text) => {
  return goog.dom.safeHtmlToNode(ns.i18nLabel(text));
};

/**
 * Get a translation dict of all locales name in respected locale.
 * For example: {'en-US': 'English', 'zh-CN': '中文'}
 * @return {!cros.factory.i18n.TranslationDict}
 */
ns.getLocaleNames = () => {
  // Note: this should be translated to, for example,
  // 'currentLocaleName#zh-CN#中文'.
  const dict = _('currentLocaleName#en-US#English');
  const ret = Object.create(null);
  for (const locale of ns.locales) {
    const val = dict[locale];
    const idx = val.indexOf(`#${locale}#`);
    if (idx == -1) {
      // The entry is probably not translated, fallback to use the locale
      // name.
      ret[locale] = locale;
    } else {
      ret[locale] = val.substr(idx + 2 + locale.length);
    }
  }
  return ret;
};

/**
 * Wrapper for i18n string processing.
 *
 * This acts as translation when dict is not given, and stringFormat when dict
 * is given.
 * @param {string|!cros.factory.i18n.TranslationDict} format the format
 *     string.
 * @param {?Object<string, string>=} dict the arguments in format string.
 * @return {!cros.factory.i18n.TranslationDict}
 */
ns._ = (format, dict = null) => {
  if (dict == null) {
    return ns.translation(goog.asserts.assertString(format));
  }
  return ns.stringFormat(format, dict);
};

});

/**
 * @export
 */
const _ = cros.factory.i18n._.bind(cros.factory.i18n);
