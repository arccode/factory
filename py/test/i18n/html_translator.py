# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for translation related methods for HTML."""

import cgi
import HTMLParser
import re
import StringIO

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import translation
from cros.factory.test.i18n.translation import _


class BaseHTMLTransformer(HTMLParser.HTMLParser, object):
  """Class that pass the input HTML untransformed to output.

  This is used as a base class for various transforms.
  """
  def __init__(self):
    super(BaseHTMLTransformer, self).__init__()
    self.out_fp = StringIO.StringIO()

  def _EmitOutput(self, output):
    self.out_fp.write(output)

  def _AddKeyValueToAttrs(self, attrs, key, value):
    result = []
    done = False
    for attr in attrs:
      if done:
        result.append(attr)
        continue
      if attr[0] == key:
        result.append((attr[0], attr[1] + ' ' + value))
        done = True
      else:
        result.append(attr)
    if not done:
      result.append((key, value))
    return result

  def _MakeStartTag(self, tag, attrs, self_closing=False):
    attrs_str = ''.join(' %s="%s"' % (key, cgi.escape(value, quote=True))
                        for key, value in attrs)
    return '<%s%s%s>' % (tag, attrs_str, '/' if self_closing else '')

  def handle_starttag(self, tag, attrs):
    self._EmitOutput(self._MakeStartTag(tag, attrs))

  def handle_endtag(self, tag):
    self._EmitOutput('</%s>' % tag)

  def handle_startendtag(self, tag, attrs):
    self._EmitOutput(self._MakeStartTag(tag, attrs, self_closing=True))

  def handle_data(self, data):
    self._EmitOutput(data)

  def handle_entityref(self, name):
    self._EmitOutput('&%s;' % name)

  def handle_charref(self, name):
    self._EmitOutput('&#%s;' % name)

  def handle_comment(self, data):
    self._EmitOutput('<!--%s-->' % data)

  def handle_decl(self, decl):
    self._EmitOutput('<!%s>' % decl)

  def handle_pi(self, data):
    self._EmitOutput('<?%s>' % data)

  def unknown_decl(self, data):
    self._EmitOutput('<![%s]>' % data)

  def close(self):
    super(BaseHTMLTransformer, self).close()

  def GetOutput(self):
    """Get the output HTML."""
    return self.out_fp.getvalue()

  def Run(self, html):
    """Transform the given HTML.

    This should only be called on a new instance, and would close the
    HTMLParser, so it can't be reused.

    Args:
      html: The string of HTML to be transformed.

    Returns:
      A string representing the transformed HTML.
    """
    self.feed(html)
    self.close()
    return self.GetOutput()


VOID_ELEMENTS = ['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                 'keygen', 'link', 'menuitem', 'meta', 'param', 'source',
                 'track', 'wbr']


class HTMLTranslator(BaseHTMLTransformer):
  """Class for doing HTML translation.

  Example::
    translator = HTMLTranslator()
    translated_html = translator.Run(html)
  """
  def __init__(self, keyword_classes=None):
    super(HTMLTranslator, self).__init__()
    if keyword_classes is None:
      keyword_classes = ['i18n-label']
    self.keyword_classes = set(keyword_classes)
    self.tags = []
    self.data = []
    self.in_keyword_tag = False

  def _EmitOutput(self, output):
    if self.in_keyword_tag:
      self.data.append(output)
    else:
      self.out_fp.write(output)

  def handle_starttag(self, tag, attrs):
    if tag not in VOID_ELEMENTS:
      if self.in_keyword_tag:
        self.tags.append((tag, False, attrs))
      else:
        classes = ' '.join(value for key, value in attrs if key == 'class')
        classes = classes.split()
        is_keyword = any(cls in self.keyword_classes for cls in classes)
        self.tags.append((tag, is_keyword, attrs))
        if is_keyword:
          self.in_keyword_tag = True
          return

    super(HTMLTranslator, self).handle_starttag(tag, attrs)

  def handle_endtag(self, tag):
    if tag not in VOID_ELEMENTS:
      open_tag, is_keyword, attrs = self.tags.pop()
      if open_tag != tag:
        row, col = self.getpos()
        raise ValueError('%s,%s: Unexpected close tag, expected %s, got %s.' % (
            row, col, open_tag, tag))

      if is_keyword:
        msg = ''.join(self.data).strip()
        self.data = []
        self.in_keyword_tag = False

        msg = _(msg)
        for locale in translation.LOCALES:
          text = msg[locale]
          start_tag = self._MakeStartTag(
              tag, self._AddKeyValueToAttrs(
                  attrs, 'class', 'goofy-label-%s' % locale))
          end_tag = '</%s>' % tag
          self._EmitOutput(start_tag + text + end_tag)
        return

    super(HTMLTranslator, self).handle_endtag(tag)

  def handle_data(self, data):
    if self.in_keyword_tag:
      self.data.append(re.sub(r'\s+', ' ', data))
    else:
      self.out_fp.write(data)

  def close(self):
    super(HTMLTranslator, self).close()
    if self.tags:
      raise ValueError('Found unclosed tags: %r' % ([t[0] for t in self.tags]))


def TranslateHTML(html, keyword_classes=None):
  """Translate the given static HTML.

  All tags that has class inside keyword_classes would be cloned once for each
  locales, and the HTML inside the tag would be replaced with translated
  version. Also, class "goofy-label-${locale}" would be added to the tag.

  See testdata/html_translator/{input,output}.html for example input and
  output of this function.

  Args:
    html: The string of HTML to be translated.
    keyword_classes: An array of class names that contains text that need to be
        translated. Default is ['i18n-label'].

  Returns:
    A string representing the translated HTML.

  Raises:
    ValueError: If the input HTML contains unbalanced tag.
  """
  return HTMLTranslator(keyword_classes).Run(html)
