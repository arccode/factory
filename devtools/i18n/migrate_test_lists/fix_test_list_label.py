# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
This module contains fixer to migrate some common test list items to new i18n
format. See class FixTestListLabel for detail.
"""

import ast
from lib2to3 import fixer_base
from lib2to3 import fixer_util
from lib2to3.fixer_util import Comma
from lib2to3.fixer_util import Leaf
from lib2to3.fixer_util import LParen
from lib2to3.fixer_util import Name
from lib2to3.fixer_util import Node
from lib2to3.fixer_util import RParen
from lib2to3.fixer_util import String
from lib2to3.pgen2 import token
from lib2to3.pygram import python_symbols as syms


def GetSimpleString(node):
  if node.type != token.STRING:
    return None
  value = ast.literal_eval(node.value)
  if isinstance(value, str):
    value = value.decode('UTF-8')
  return value


class Dictionary(object):
  """The base class for a dictionary-like view of AST nodes."""
  def Get(self, key):
    """Get the "value object" for the correspond key, or None if not found."""
    raise NotImplementedError

  def GetKeys(self):
    """Get all keys."""
    raise NotImplementedError

  def GetString(self, value):
    """Get the python unicode string corresponds to the value.

    None is returned if the value is not a literal string.
    """
    raise NotImplementedError

  def Remove(self, key):
    """Remove the key from dictionary."""
    raise NotImplementedError

  def Insert(self, key, value, after_key):
    """Insert a key-value pair to the dictionary in a location.

    value would be wrapped in a _().
    """
    raise NotImplementedError


class FunctionArgumentDictionary(Dictionary):
  """A view of function arguments as dictionary.

  This class handle the case like dict(xxx_en='foo', xxx_zh='bar').
  The arg_list got in initializer would be the ast node corresponds to the part
  `xxx_en='foo', xxx_zh='bar'`.
  """
  def __init__(self, arg_list):
    self.arg_list = arg_list
    self.arg_map = {}
    for child in arg_list.children:
      if child.type != syms.argument:
        continue
      if len(child.children) != 3:
        continue
      name, sep, unused_value = child.children
      if name.type != token.NAME or sep.type != token.EQUAL:
        continue
      self.arg_map[name.value] = child

  def Get(self, key):
    return self.arg_map.get(key)

  def GetString(self, value):
    return GetSimpleString(value.children[2])

  def GetKeys(self):
    return self.arg_map.keys()

  def Remove(self, key):
    if key not in self.arg_map:
      return
    node = self.arg_map[key]
    next_node = node.next_sibling
    if next_node is not None and next_node.type == token.COMMA:
      next_node.remove()
    else:
      prev_node = node.prev_sibling
      if prev_node is not None and prev_node.type == token.COMMA:
        prev_node.remove()
    return node.remove()

  def Insert(self, key, value, after_key):
    new_arg = Node(syms.argument, [
        Name(key), Leaf(token.EQUAL, u'='), Node(syms.power, [
            Name(u'_'),
            Node(syms.trailer,
                 [LParen(), String(value.children[2].value), RParen()])
        ])
    ])
    node = self.arg_map[after_key]
    idx = self.arg_list.children.index(node)
    self.arg_list.insert_child(idx + 1, Comma())
    self.arg_list.insert_child(idx + 2, new_arg)


class DictLiteralDictionary(Dictionary):
  """A view of dict literal as dictionary.

  This class handle the case {'xxx_en': 'foo', 'xxx_zh': 'bar'}.
  The dict_list got in initializer would be the ast node corresponds to the part
  `'xxx_en': 'foo', 'xxx_zh': 'bar'`.
  """
  def __init__(self, dict_list):
    self.dict_list = dict_list
    self.arg_map = {}
    children = dict_list.children
    for idx, child in enumerate(children):
      if idx + 2 >= len(children):
        break
      if child.type != token.STRING or children[idx + 1].type != token.COLON:
        continue
      self.arg_map[ast.literal_eval(child.value)] = children[idx + 2]

  def GetKeys(self):
    return self.arg_map.keys()

  def Get(self, key):
    return self.arg_map.get(key)

  def GetString(self, value):
    return GetSimpleString(value)

  def Remove(self, key):
    if key not in self.arg_map:
      return
    node = self.arg_map[key]
    colon_node = node.prev_sibling
    name_node = colon_node.prev_sibling
    next_node = node.next_sibling
    if next_node is not None and next_node.type == token.COMMA:
      next_node.remove()
    else:
      prev_node = name_node.prev_sibling
      if prev_node is not None and prev_node.type == token.COMMA:
        prev_node.remove()
    node.remove()
    colon_node.remove()
    name_node.remove()

  def Insert(self, key, value, after_key):
    value = Node(syms.power, [
        Name(u'_'), Node(syms.trailer,
                         [LParen(), String(value.value), RParen()])
    ])

    node = self.arg_map[after_key]
    idx = self.dict_list.children.index(node)
    self.dict_list.insert_child(idx + 1, Comma())
    self.dict_list.insert_child(idx + 2, String(repr(key)))
    self.dict_list.insert_child(idx + 3, Leaf(token.COLON, u':'))
    self.dict_list.insert_child(idx + 4, value)


class FixTestListLabel(fixer_base.BaseFix):
  """The main fixer class.

  The class would migrate some common items in test lists to new i18n format.
  It would fix the following:
  * FactoryTest(id=..., label_en=..., label_zh=...)
  * dargs=dict(xxx_en=..., xxx_zh=...)
  * dargs={'xxx_en': ..., 'xxx_zh': ...}
  """
  FUNC_NAME = (
      "('FactoryTest' | 'OperatorTest' | 'AutomatedSequence' | 'RebootStep' "
      "| 'HaltStep')")

  PATTERN = r"""
    power< name={func_name} trailer< '(' arg_list=any ')' > >
    |
    argument< 'dargs' '=' power< 'dict' trailer< '(' arg_list=any ')' > > >
    |
    argument< 'dargs' '=' atom< '{{' dict_list=any '}}' > >
    |
    expr_stmt< 'dargs' '=' power< 'dict' trailer< '(' arg_list=any ')' > > >
    |
    expr_stmt< 'dargs' '=' atom< '{{' dict_list=any '}}' > >
  """.format(func_name=FUNC_NAME)

  def __init__(self, options, log):
    super(FixTestListLabel, self).__init__(options, log)
    self.i18n_messages = []

  def ExtractI18nAndTransform(self,
                              parent,
                              key,
                              arg_dict,
                              fallback_key=None):
    en_key = key + '_en'
    zh_key = key + '_zh'
    fallback_arg = arg_dict.Get(fallback_key)
    label_en_arg = arg_dict.Get(en_key)
    label_zh_arg = arg_dict.Get(zh_key)

    if label_en_arg is None and label_zh_arg is None:
      return

    if label_en_arg is not None:
      en_arg = label_en_arg
      en_arg_key = en_key
    else:
      en_arg = fallback_arg
      en_arg_key = fallback_key

    if en_arg is None:
      self.warning(parent, "Contains %s but no %s..." % (zh_key, en_key))
      return

    en = arg_dict.GetString(en_arg)
    if en is None:
      self.warning(parent,
                   "Argument for '%s' is not string literal, skipping..." %
                   en_arg_key)
      return

    if label_zh_arg is not None:
      zh_arg = label_zh_arg
      zh_arg_key = zh_key
    else:
      zh_arg = en_arg
      zh_arg_key = en_arg_key

    zh = arg_dict.GetString(zh_arg)
    if zh is None:
      self.warning(parent,
                   "Argument for '%s' is not string literal, skipping..." %
                   zh_arg_key)
      return

    self.i18n_messages.append(((self.filename, parent.get_lineno()),
                               (en, zh)))

    arg_dict.Insert(key, en_arg, en_arg_key)
    arg_dict.Remove(zh_key)
    arg_dict.Remove(en_key)
    fixer_util.touch_import('cros.factory.test.i18n', '_', parent)

  def transform(self, node, results):
    if 'arg_list' in results:
      arg_dict = FunctionArgumentDictionary(results['arg_list'])
    else:
      arg_dict = DictLiteralDictionary(results['dict_list'])

    if 'name' in results:
      # test_list case
      self.ExtractI18nAndTransform(node, 'label', arg_dict, fallback_key='id')
    else:
      # dargs case
      todo_list = set()
      for key in arg_dict.GetKeys():
        if key.endswith('_en') or key.endswith('_zh'):
          todo_list.add(key[:-3])

      if not todo_list:
        return

      for todo_key in todo_list:
        self.ExtractI18nAndTransform(node, todo_key, arg_dict)
