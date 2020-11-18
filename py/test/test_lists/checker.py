# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import ast
import builtins
import copy
import inspect

from cros.factory.test.test_lists import test_list as test_list_module
from cros.factory.test.utils import pytest_utils
from cros.factory.utils import arg_utils
from cros.factory.utils import type_utils


_EVALUATE_PREFIX = test_list_module.EVALUATE_PREFIX


class UnresolvableNamespace:
  """A stub namespace.

  Accessing anything under the namespace will cause an UnresolvableException.
  """
  def __init__(self):
    # for state_proxy.data_shelf.device
    self.data_shelf = self
    self.data_shelf.device = self

  def __getattr__(self, attr_name):
    raise UnresolvableException

  def __getitem__(self, key):
    raise UnresolvableException


class UnresolvableException(Exception):
  """We cannot resolve something (statically)."""


class UnresolvableValue:
  """This value cannot be resolved by checker."""
  def __init__(self, eval_string):
    self.eval_string = eval_string


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


class Checker:
  """Check if a test list is valid.

  This class implements functions that help you to find test list errors
  *before* actually running tests in the test list.
  """

  _EVAL_VALID_IDENTIFIERS = set(
      ['constants', 'options', 'dut', 'station', 'state_proxy', 'locals',
       'device'] +
      [key for key, unused_value in inspect.getmembers(builtins)])

  _RUN_IF_VALID_IDENTIFIERS = set(
      ['constants', 'device'] +
      [key for key, unused_value in inspect.getmembers(builtins)])

  def AssertValidArgs(self, args):
    """Check if the "eval! " expressions in an argument is valid."""
    if not isinstance(args, dict):
      return

    for value in args.values():
      if isinstance(value, str):
        if value.startswith(_EVALUATE_PREFIX):
          self.AssertValidEval(value[len(_EVALUATE_PREFIX):])
      else:
        self.AssertValidArgs(value)

  def AssertValidEval(self, expression):
    """Check if an expression from "eval! ..." is valid.

    This function calls `self.AssertExpressionIsValid` to parse and collect free
    variables in the expression.  We only allows the following identifiers:
      - built-in functions
      - "constants" and "options" defined by test list
      - "dut", "station" (to get information from DUT and station)
      - "locals" the `locals_` attribute of current test
      - "state_proxy" (state server proxy returned by state.GetInstance())
      - "device" (a short cut for `state_proxy.data_shelf.device`)

    Args:
      :type expression: str
    """
    return self._AssertValidExpression(
        expression, self._EVAL_VALID_IDENTIFIERS)

  def AssertValidRunIf(self, run_if):
    return self._AssertValidExpression(run_if, self._RUN_IF_VALID_IDENTIFIERS)

  def _AssertValidExpression(self, expression, valid_identifiers):
    """Raise an expression if this expression is not allowed.

    The expression is a snippet of python code, which,

      * Is a single expression (not necessary single line, but the parsed result
        is a single expression)
      * Not all operators are allowed, you cannot use generator or create lambda
        functions.

    This function will raise an exception if you are using an undefined
    variable, e.g. `[x for x in undefined_var]`.  We also assume that target
    variables in list comprehension does not leak into local namespace.
    Therefore, the expression `([x for x in [1]], x)` will be rejected, even
    though it is a valid expression in Python2.  See TestListExpressionVisitor
    for more details.

    Collected free variables must be a subset of `valid_identifiers`.

    Args:
      :type expression: str
      :type valid_identifiers: set
    """
    try:
      syntax_tree = ast.parse(expression, filename=repr(expression),
                              mode='eval')
    except SyntaxError as e:
      raise CheckerError(e)

    collector = TestListExpressionVisitor()
    # collect all variables, might raise an exception if there are invalid nodes
    collector.visit(syntax_tree)
    undefined_identifiers = (collector.free_vars - valid_identifiers)

    if undefined_identifiers:
      raise CheckerError('undefined identifiers: %s' % undefined_identifiers)

  def CheckArgsType(self, test, test_list):
    """Check if the type of arguments are valid."""
    if not test.pytest_name:
      return

    pytest = pytest_utils.LoadPytest(test.pytest_name)()
    args_spec = getattr(pytest, 'ARGS', None)
    if not args_spec:
      # no argument for this pytest
      if test.dargs:
        raise type_utils.TestListError(
            '%s does not accept any arguments' % test.pytest_name)
      return

    for arg in args_spec:
      arg.type += (UnresolvableValue, )

    args_spec = arg_utils.Args(*args_spec)

    resolved_args = self.StaticallyResolveTestArgs(test, test_list)
    args_spec.Parse(resolved_args, unresolvable_type=UnresolvableValue)

  def StaticallyResolveTestArgs(self, test, test_list):
    """Resolve test args without accessing DUT or station.

    Args:
      test: the test object whose dargs will be resolved.
      :type test: cros.factory.test.test_lists.test_object.FactoryTest
      test_list: the test list this test object belongs to.
      :type test_list: cros.factory.test.test_lists.manager.ITestList
    """
    unresolvable_namespace = UnresolvableNamespace()

    resolved_args = {}

    for key, value in test.dargs.items():
      try:
        tmp_dict = test_list.ResolveTestArgs(
            {key: value}, locals_=test.locals_,
            # dut, station, state_proxy are not available while resolving.
            dut=unresolvable_namespace,
            station=unresolvable_namespace,
            state_proxy=unresolvable_namespace)
        resolved_value = tmp_dict[key]
      except UnresolvableException:
        resolved_value = UnresolvableValue(value)
      resolved_args[key] = resolved_value
    return resolved_args
