#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Loader of test_list.json"""

import __builtin__
import ast
import copy
import inspect

import factory_common  # pylint: disable=unused-import


class Loader(object):
  """Helper class to load a test list from given directory.

  The loader only loads the test list for you, an exception will be raised if
  jsonschema check failed.
  """
  # TODO(stimim): implement this class


class CheckerError(Exception):
  """An exception raised by `Checker`"""


class TestListExpressionVisitor(ast.NodeVisitor):
  """Collects free variables of an expression.

  Usage::

    collector = TestListExpressionVisitor()
    collector.visit(ast_node)

  ast_node should be a single ast.Expression.
  """
  def __init__(self):
    super(TestListExpressionVisitor, self).__init__()
    self.free_vars = set()
    self.bounded_vars = set()

  def visit_Name(self, node):
    if isinstance(node.ctx, ast.Load) and node.id not in self.bounded_vars:
      self.free_vars.add(node.id)
    elif isinstance(node.ctx, ast.Store):
      self.bounded_vars.add(node.id)
    self.generic_visit(node)

  def visit_ListComp(self, node):
    self._VisitComprehension(node)

  def visit_SetComp(self, node):
    self._VisitComprehension(node)

  def visit_DictComp(self, node):
    self._VisitComprehension(node)

  def _VisitComprehension(self, node):
    """visit a XXXComp object.

    We override default behavior because we need to make sure elements and
    generators are visited in correct order (generators first, and then
    elements)

    `node` is either a `ListComp` or `DictComp` or `SetComp` object.
    """
    bounded_vars_bak = copy.copy(self.bounded_vars)

    if isinstance(node, ast.DictComp):
      elements = [node.key, node.value]
    else:
      elements = [node.elt]

    for generator in node.generators:
      self.visit(generator)
    for element in elements:
      self.visit(element)

    # The target variables defined in list comprehension pollutes local
    # namespace while set comprehension and dict comprehension doesn't.
    # e.g. ([x for x in [1]], x) ==> ([1], 1)
    #      ({x for x in [1]}, x) ==> x is undefined
    #      ({x: 1 for x in [1]}, x) ==> x is undefined
    # We *can* implement this behavior, but it would be more simple if we assume
    # that target variables in comprehension can't pollute local namespace.
    # Otherwise we need to handle corner cases like:
    #
    #   {x for u in {(x, y) for y in [x for x in [1]]}} === set([1])
    #   {y for u in {(x, y) for y in [x for x in [1]]}} ==> undefined y
    #
    # Restore self.bounded_vars.
    self.bounded_vars = bounded_vars_bak

  # Reject nodes we don't like
  # Lambda is invalid because we cannot serialize a lambda function.
  def visit_Lambda(self, node):
    del node  # unused
    raise CheckerError('lambda function is not allowed')

  # GeneratorExp is invalid because we cannot serialize it.
  def visit_GeneratorExp(self, node):
    del node  # unused
    raise CheckerError('generator is not allowed')

  # Yield is invalid because you should not be able to define a Yield
  # expression with only one line.
  def visit_Yield(self, node):
    del node  # unused
    raise CheckerError('yield is not allowed')


class Checker(object):
  """Check if a test list is valid.

  This class implements functions that help you to find test list errors
  *before* actually running tests in the test list.
  """
  def __init__(self, manager):
    self.manager = manager

  _EXPRESSION_VALID_IDENTIFIERS = set(
      ['constants', 'options', 'dut', 'station', 'session'] +
      [key for key, unused_value in inspect.getmembers(__builtin__)])

  def AssertExpressionIsValid(self, expression):
    """Raise an expression if this expression is not allowed.

    The expression is a snippet of python code, which,

      * Is a single expression (not necessary single line, but the parsed result
        is a single expression)
      * Not all operators are allowed, you cannot use generator or create lambda
        functions.
      * When executing, the namespace would only contains:
        - built-in functions
        - "constants" and "options" defined by test list
        - "dut", "station" (to get information from DUT and station)
        - "session" (session is not implemented yet, it will represent a test
          session on a test station)

    This function will raise an exception if you are using an undefined
    variable, e.g. `[x for x in undefined_var]`.  We also assume that target
    variables in list comprehension does not leak into local namespace.
    Therefore, the expression `([x for x in [1]], x)` will be rejected, even
    though it is a valid expression in Python2.  See TestListExpressionVisitor
    for more details.

    Args:
      :type expression: basestring
    """
    try:
      syntax_tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
      raise CheckerError(e)

    collector = TestListExpressionVisitor()
    # collect all variables, might raise an exception if there are invalid nodes
    collector.visit(syntax_tree)
    undefined_identifiers = (
        collector.free_vars - self._EXPRESSION_VALID_IDENTIFIERS)

    if undefined_identifiers:
      raise CheckerError('undefined identifiers: %s' % undefined_identifiers)


class Manager(object):
  """Test List Manager.

  Attributes:
    test_configs: a dict maps a string (test list id) to loaded config file.
      Each loaded config file is just a json object, haven't been checked by
      `Checker` or merged with base test lists.
    test_lists: a dict maps a string (test list id) to loaded test list.
      Each loaded test list is a FactoryTestList object (or acts like one), have
      merged with base test lists and passed checker.
  """
  def __init__(self, loader=None, checker=None):
    self.loader = loader or Loader()
    self.checker = checker or Checker(self)

    self.test_configs = {}
    self.test_lists = {}

  # TODO(stimim): implement this class.
