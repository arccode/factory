# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A text buffer that prepends indentation."""


class IndentTextWriter(object):
  """A text buffer that prepends indentation.

  It buffers input lines and output with specified indentation when Flush()
  is called. It accepts following actions:
    1) add a line;
    2) increase / decrease indentation level;
    3) enter / exit a block.

  For example, if you want to add a block from top with indentation space four,
  like this:
  (
      block line 1
      block line 2
  )

  The code is:
    writer = IndentTextWriter(indent_space=4, indent_first_line=True)
    writer.EnterBlock('()')
    writer.Write('block line 1')
    writer.Write('block line 2')
    print writer.Flush()

  Its constructor can specify the initial indentation level, indentation
  spaces, and if it should indent the first line.
  """

  def __init__(self, indent=0, indent_space=2, indent_first_line=True):
    """Constructor.

    Args:
      indent: initial indentation level.
      indent_space: indentation space.
      indent_first_line: should indent the first line or not.
    """
    self._indent_base = indent
    self._indent_space = indent_space
    self._indent_first_line = indent_first_line
    self._lines = []
    self._indent = self._indent_base
    self._close_brackets = []

  def Reset(self):
    """Resets states.

    Resets indentation level to the value specified in ctor, and empties input
    buffer.
    """
    self._lines = []
    self._indent = self._indent_base
    self._close_brackets = []

  def IncIndent(self):
    """Increases indentation level."""
    self._indent += self._indent_space

  def DecIndent(self):
    """Decreases indentation level.

    Lowerst indentation level is indent specified in ctor."""
    self._indent = max(self._indent_base, self._indent - self._indent_space)

  def EnterBlock(self, bracket=None):
    """Enters a block with optional bracket pairs.

    It adds open bracket before increasing indent and saves close bracket to
    a stack for ExitBlock() to pop out.

    Args:
      bracket: (optional) Pair of open and close bracket symbol.
    """
    if bracket:
      self.Write(bracket[0])
    self.IncIndent()
    self._close_brackets.append(bracket[1] if bracket else None)

  def ExitBlock(self):
    """Exits a block.

    It decreases an indentation level and adds a close bracket if available.
    """
    self.DecIndent()
    close_bracket = self._close_brackets.pop()
    if close_bracket:
      self.Write(close_bracket)

  def Write(self, line):
    """Writes a line to buffer.

    Args:
      line: a string without '\n' to be appended as a line.
    """
    if self._lines or self._indent_first_line:
      self._lines.append(' ' * self._indent + line)
    else:
      self._lines.append(line)

  def Flush(self):
    """Flushes input buffer."""
    result = '\n'.join(self._lines)
    self.Reset()
    return result

  @staticmethod
  def Factory(writer):
    """Factory method that creates a writer based on the given object.

    Except the input buffer, it copies indent, indent_space and
    indent_first_line properties from the given object.

    Args:
      writer: a IndexTextWriter object.
    """
    # pylint: disable=W0212
    return IndentTextWriter(indent=writer._indent,
                            indent_space=writer._indent_space,
                            indent_first_line=writer._indent_first_line)
