# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


class Option:
  """Utility class for generating and manipulating HTML option tag.

  Args:
    value: Text value of the option. This is the value inside option tag.
    display: Displayed value of the option. This is the value shown on page.
    selected: Boolean value indicating whether this option is selected.
  """

  def __init__(self, value, display, selected=False):
    self._value = value
    self._display = display
    self._selected = selected

  def SetSelected(self, value):
    """Set selected attribute

    Args:
      value: A boolean value indicating the selected status.
    """
    self._selected = value

  def GenerateHTML(self):
    """Generate HTML tag."""
    attrs = 'value="%s"' % self._value
    if self._selected:
      attrs += ' selected'
    return ['<option %s>' % attrs, self._display, '</option>']


class SelectBox:
  """Utility class for generating and manipulating HTML select box and options.

  Args:
    id: ID of the select box.
    size: The size of the select box.
    style: CSS style to apply on the select box.
  """

  def __init__(self, element_id, size=10, style=None):
    self._element_id = element_id
    self._size = size
    self._style = style
    self._option_list = []

  def AppendOption(self, value, display):
    """Appends a option into the select box.

    Args:
      value: Text value of the option. This is the value inside option tag.
      display: Displayed value of the option. This is the value shown on page.
    """
    self._option_list.append(Option(value, display))

  def SetSelectedIndex(self, index):
    """Set the given index as selected."""
    if len(self._option_list) < index:
      return
    self._option_list[index].SetSelected(True)

  def GenerateHTML(self):
    """Generate HTML tags."""
    html = ['<select id="%s" size=%d style="%s">' % (
        self._element_id, self._size, self._style)]
    for option in self._option_list:
      html.append(option.GenerateHTML())
    html.append('</select>')
    return html


class Table:
  """Utility class for generating HTML table.

  This class allows us to easily set the content of each cell. For example:

    table = Table(element_id='example_table', rows=2, cols=2)
    for r in range(2):
      for c in range(2):
        table.SetContent(r, c, 'row %d col %d' % (r, c))
    return table.GenerateHTML()

  Args:
    element_id: ID of the table.
    rows: Number of rows.
    cols: Number of columns.
    style: CSS style to apply on the table.
  """

  def __init__(self, element_id=None, rows=1, cols=1, style=None):
    self._element_id = element_id or ''
    self._style = style or ''
    self._content = {}
    self.rows = rows
    self.cols = cols

  def SetContent(self, row, col, content):
    """Sets HTML content of specified row and column."""
    self._content[(row, col)] = content

  def GenerateHTML(self):
    """Generates HTML tags."""
    html = ['<table id="%s" style="%s">' % (self._element_id, self._style)]
    for r in range(self.rows):
      html.append('<tr>')
      for c in range(self.cols):
        html.append('<td>')
        if (r, c) in self._content:
          html.append(self._content[(r, c)])
        html.append('</td>')
      html.append('</tr>')
    html.append('</table>')
    return html
