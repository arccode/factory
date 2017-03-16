// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.i18n');

goog.require('goog.dom');
goog.require('goog.html.SafeHtml');

/**
 * @typedef {function(!Object<string, string>): string}
 */
cros.factory.i18n.FormatFunc;

/**
 * @type {!Object<string, cros.factory.i18n.FormatFunc>}
 */
cros.factory.i18n.formatCache = Object.create(null);

/**
 * Parse the format string and return the function for formatting.
 * This function emulates what python str.format() does.
 * @param {string} format the format string.
 * @return {cros.factory.i18n.FormatFunc}
 */
cros.factory.i18n.stringFormatImpl = function(format) {
  let /** Array<string> */ strs = [''];
  let /** Array<string> */ vars = [];
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
  return (function(/** !Object<string, string> */ dict) {
    let ret = strs[0];
    for (let i = 0; i < vars.length; i++) {
      ret += dict[vars[i]];
      ret += strs[i + 1];
    }
    return ret;
  });
};

/**
 * Cached version for cros.factory.i18n.stringFormatImpl.
 * @param {string} format the format string.
 * @return {cros.factory.i18n.FormatFunc}
 */
cros.factory.i18n.stringFormatCached = function(format) {
  if (!(format in cros.factory.i18n.formatCache)) {
    cros.factory.i18n.formatCache[format] =
        cros.factory.i18n.stringFormatImpl(format);
  }
  return cros.factory.i18n.formatCache[format];
};

/**
 * Most of the following functions have same signatures with the corresponding
 * methods in python module cros.factory.test.i18n.*.
 * See document there for more detailed explanation.
 */

/**
 * Type that most i18n functions return.
 * @typedef {!Object<string, string>}
 */
cros.factory.i18n.TranslationDict;

/**
 * Default locale to use when no translation found.
 * @type {string}
 * @const
 */
cros.factory.i18n.DEFAULT_LOCALE = 'en-US';

/**
 * All support locales.
 * @type {!Array<string>}
 */
cros.factory.i18n.locales = [cros.factory.i18n.DEFAULT_LOCALE];

/**
 * Dictionary that contains all translations.
 * @type {!Object<string, cros.factory.i18n.TranslationDict>}
 * @private
 */
cros.factory.i18n.translations_ = Object.create(null);
if (window['goofy_i18n_data']) {
  cros.factory.i18n.locales = window['goofy_i18n_data']['locales'];
  for (const text of /** @type !Array<cros.factory.i18n.TranslationDict> */ (
           window['goofy_i18n_data']['translations'])) {
    const key = text[cros.factory.i18n.DEFAULT_LOCALE];
    cros.factory.i18n.translations_[key] = text;
  }
}

/**
 * Returns a text untranslated for all locales.
 * @param {string} text
 * @return {cros.factory.i18n.TranslationDict}
 */
cros.factory.i18n.noTranslation = function(text) {
  const ret = Object.create(null);
  for (const locale of cros.factory.i18n.locales) {
    ret[locale] = text;
  }
  return ret;
};

/**
 * Returns a text translated.
 * @param {string} text the text to be translated.
 * @return {cros.factory.i18n.TranslationDict}
 */
cros.factory.i18n.translation = function(text) {
  if (text in cros.factory.i18n.translations_) {
    return cros.factory.i18n.translations_[text];
  } else {
    return cros.factory.i18n.noTranslation(text);
  }
};

/**
 * Make sure the input is a TranslationDict, pass it to translation or
 * noTranslation if it isn't, based on the value of argument translate.
 * @param {cros.factory.i18n.TranslationDict|string} obj
 * @param {boolean=} translate whether string should be passed to translation or
 *     noTranslation.
 * @return {cros.factory.i18n.TranslationDict}
 */
cros.factory.i18n.translated = function(obj, translate = true) {
  // Because of type checking for dict object is MUCH harder in JS, we assume
  // that passed in obj is a TranslationDict if it's an object.
  if (typeof obj === 'object') {
    const ret = Object.create(null);
    for (const locale of cros.factory.i18n.locales) {
      ret[locale] =
          (locale in obj) ? obj[locale] : obj[cros.factory.i18n.DEFAULT_LOCALE];
    }
    return ret;
  } else {
    return translate ? cros.factory.i18n.translation(obj) :
                       cros.factory.i18n.noTranslation(obj);
  }
};

/**
 * Do python-like i18n string format.
 * @param {string|cros.factory.i18n.TranslationDict} format the format string.
 * @param {!Object<string, string>} dict the arguments in format string.
 * @return {cros.factory.i18n.TranslationDict}
 */
cros.factory.i18n.stringFormat = function(format, dict) {
  const format_dict = cros.factory.i18n.translated(format);
  const translated_dict = Object.create(null);
  for (const key of Object.keys(dict)) {
    translated_dict[key] = cros.factory.i18n.translated(dict[key], false);
  }
  const ret = Object.create(null);
  for (const locale of cros.factory.i18n.locales) {
    const args = Object.create(null);
    for (const key of Object.keys(translated_dict)) {
      args[key] = translated_dict[key][locale];
    }
    ret[locale] =
        cros.factory.i18n.stringFormatCached(format_dict[locale])(args);
  }
  return ret;
};

/**
 * Make a translated label.
 * @param {string|cros.factory.i18n.TranslationDict} text
 * @param {!Object<string, string>=} dict
 * @return {!goog.html.SafeHtml}
 */
cros.factory.i18n.i18nLabel = function(text, dict = {}) {
  let label = cros.factory.i18n.stringFormat(text, dict);
  let children = [];
  for (const locale of cros.factory.i18n.locales) {
    const translated_label = label[locale];
    const html_class = 'goofy-label-' + locale;
    children.push(goog.html.SafeHtml.create(
        'span', {class: html_class}, translated_label));
  }
  return goog.html.SafeHtml.concat(children);
};

/**
 * Make a translated label.
 * @param {string|cros.factory.i18n.TranslationDict} text
 * @param {!Object<string, string>=} dict
 * @return {!Node}
 */
cros.factory.i18n.i18nLabelNode = function(text, dict = {}) {
  return goog.dom.safeHtmlToNode(cros.factory.i18n.i18nLabel(text, dict));
};
