# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging


class Option(object):
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
    return '<option value="%s"%s>%s</option>' % (
        self._value, ' selected' if self._selected else '', self._display)


class SelectBox(object):
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
      html += [option.GenerateHTML()]
    html += ['</select>']
    return '\n'.join(html)


class Table(object):
  """Utility class for generating HTML table.

  This class allows us to easily set the content of each cell. For example:

    table = Table(element_id='example_table', rows=2, cols=2)
    for r in xrange(2):
      for c in xrange(2):
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
    html = ['<table id="%s" style="%s">' % (
        self._element_id, self._style)]
    for r in xrange(self.rows):
      html.append('<tr>')
      for c in xrange(self.cols):
        html.append('<td>')
        if (r, c) in self._content:
          html.append(self._content[(r, c)])
        html.append('</td>')
      html.append('</tr>')
    html.append('</table>')
    return ''.join(html)


class BaseTemplate(object):
  """Base class for test UI template."""

  def __init__(self, ui, template_name, extra_classes=''):
    self._ui = ui

    extra_attrs = ''
    if extra_classes:
      extra_attrs = ' class="%s"' % extra_classes

    self._ui.SetHTML('<{tag}{extra_attrs}></{tag}>'.format(
        tag=template_name, extra_attrs=extra_attrs))

  def SetTitle(self, html):
    """Sets the title of the test UI.

    Args:
      html: The html content to write.
    """
    self._ui.CallJSFunction('window.template.setTitle', html)

  def SetState(self, html, append=False):
    """Sets the state section in the test UI.

    Args:
      html: The html to write.
      append: Append html at the end.
    """
    self._ui.CallJSFunction('window.template.setState', html, append)


class OneSection(BaseTemplate):
  """A simple template that has only one big section.

  This is a simple template which is suitable for tests that do not
  require showing much information.

  This template provides the following sections:

  * SetTitle: For the title of the test.
  * SetState: For displaying the state of the test or instructions to
    operator.
  """

  def __init__(self, ui):
    super(OneSection, self).__init__(ui, 'template-one-section')


class OneScrollableSection(BaseTemplate):
  """Like OneSection, but is used to show more info.

  It shows state in a scrollable element and state is left-aligned.

  This template provides the following sections:

  * SetTitle: For the title of the test.
  * SetState: For displaying the state of the test.
  """

  def __init__(self, ui):
    super(OneScrollableSection, self).__init__(ui, 'template-one-section',
                                               'scrollable')


class TwoSections(BaseTemplate):
  """A template that consists of two sections.

  The upper sections is for showing instructions to operators, and
  has a progress bar that is hidden by default. The lower section
  is for showing information regarding test state, like instructional
  pictures, or texts that indicate the progress of the test.

  This template provides the following methods:

  * SetTitle: For the title of the test.
  * SetInstruction: For displaying instructions to the operator.
  * SetState: For visually displaying the test progress.
  * DrawProgressBar, SetProgressBarValue: For showing information
    regarding the progress or state of the test. The progress bar
    is hidden by default.
  """

  def __init__(self, ui):
    super(TwoSections, self).__init__(ui, 'template-two-sections')

  def SetInstruction(self, html):
    """Sets the instruction to operator.

    Args:
      html: The html content to write.
    """
    self._ui.CallJSFunction('window.template.setInstruction', html)

  def DrawProgressBar(self):
    """Draw the progress bar and set it visible on the Chrome test UI.

    Best practice is that if the operator needs to wait more than 5 seconds,
    we should show the progress bar to indicate test progress.
    """
    self._ui.CallJSFunction('window.template.drawProgressBar')

  def SetProgressBarValue(self, value):
    """Set the value of the progress bar.

    Args:
      value: A value between 0 and 100 to indicate test progress.
    """
    self._ui.CallJSFunction('window.template.setProgressBarValue', value)


class DummyTemplate(object):
  """Dummy template for offline test."""

  def SetState(self, *args, **kargs):
    del args  # unused
    del kargs  # unused
    logging.info('Set UI state.')

  def SetTitle(self, *args, **kargs):
    del args  # unused
    del kargs  # unused
    logging.info('Set UI title')

  def SetInstruction(self, *args, **kargs):
    del args  # unused
    del kargs  # unused
    logging.info('Set UI instruction.')

  def DrawProgressBar(self):
    logging.info('Draw UI Progress Bar.')

  def SetProgressBarValue(self, value):
    logging.info('Set Progress Bar Value to %s.', value)
