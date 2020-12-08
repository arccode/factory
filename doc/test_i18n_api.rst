.. _test-i18n-api:

Test Internationalization API
=============================

.. py:module:: cros.factory.test

Overview
--------
The purpose of test internationalization (i18n) API is to have localized text
on UI of each pytest, and user can choose between different languages on UI.

Quick start
-----------
A typical workflow to add or modify text in test:

1. Depends on where the text is used, use language-specific method to mark the
   text:

  * Python: Use :func:`cros.factory.test.i18n._`::

      from cros.factory.test.i18n import _
      from cros.factory.test import test_ui

      class SomeTest(unittest.TestCaseWithUI):
        def setUp(self):
          self.ui.SetState(_('Some displayed text and should be translated.'))

  * JavaScript: Use :func:`window._` (This is automatically injected to test
    iframe by Goofy):

    .. code-block:: javascript

       const label = _('Some displayed text and should be translated.')
       window.template.appendChild(cros.factory.i18n.i18nLabelNode(label))

  * Static HTML: Use ``<i18n-label>``:

    .. code-block:: html

       <test-template>
         <i18n-label>Some displayed text and should be translated.</i18n-label>
       </test-template>

  * JSON test list items: Prefix the text with ``"i18n! "``:

    .. code-block:: json

      {
        "definitions": {
          "SomeTest": {
            "pytest_name": "some_test",
            "args": {
              "html": "i18n! Some displayed text and show be translated."
            }
          }
        }
      }

2. In chroot under ``~/trunk/src/platform/factory/po``, run:

   .. code-block:: bash

      make update

   Please refer to `Manage translation files`_ for detail if code in board
   overlay is modified, or translation of new locale should be added.

3. Edit the translation files ``~/trunk/src/platform/factory/po/*.po``.
   Currently there's only one file ``zh-CN.po`` that needs to be edited.

   The format of these files is in
   `GNU gettext PO Files
   <https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html>`_.

   Find the line similar to lines below, and add translation to it:

   .. code-block:: none

     #: ../py/test/pytests/my_awesome_test.py
     msgid "Some displayed text and should be translated."
     msgstr "The translated text, in zh-CN.po this should be Simplified Chinese"

   Also remove all ``#, fuzzy`` lines, and remove all unused lines at the end
   of file started with ``#~``.

   The po file would be bundled together with the code when factory toolkit is
   made.

4. Run ``make update`` again to make sure the po file is formatted correctly.

5. Refer to language specific section on how to use the i18n API to display the
   translated text: `I18n in Python pytest`_, `I18n in JavaScript`_, `I18n in
   static HTML`_ and `I18n in JSON test list`_. (Actually, this should already
   be done together with step 1.)

I18n in Python pytest
---------------------
All literal strings that need to be translated should be passed as the first
argument of :func:`~i18n._`.

The return value of :func:`~i18n._` is a *translation dict*, that is, a plain
python :class:`dict` with locale name as key, and translated string as value.

For example, the value of ``_('Cancel')`` is :code:`{'en-US': 'Cancel',
'zh-CN': '取消'}`. The returned translation dict can be treated as an opaque
object most of the time.

Format string in i18n text
``````````````````````````
When there are keyword argument passed to :func:`~i18n._`, the function would
do string format similar to Python :func:`str.format`. If string format is
always needed even there's no keyword argument passed, use
:func:`~i18n.StringFormat`. For example::

  self.ui.SetState(
      _('In test {test}, run {run_id}', test=_('Some test name'), run_id=1))

  if x_exists:
    format_string = _('{{x}} = {x}')
    kwargs = {'x': x}
  else:
    format_string = _('{{x}} is not here!')
    kwargs = {}
  self.ui.SetState(i18n.StringFormat(format_string, **kwargs))

Display the i18n text on UI
```````````````````````````
To display the i18n text on UI, for methods that manipulate HTML in
:class:`~test_ui.StandardUI` (:func:`~test_ui.UI.SetHTML`,
:func:`~test_ui.UI.AppendHTML`, :func:`~test_ui.StandardUI.SetTitle`,
:func:`~test_ui.StandardUI.SetState`,
:func:`~test_ui.StandardUI.SetInstruction`), the argument ``html`` accepts
either a single string as HTML, a single translation dict, or an arbitrary
nested list of either HTML string or translation dict. For example::

  self.ui.SetTitle(_('Some text'))
  # There's no need to "concatenate" the text.
  button = ['<button>', _('Click me!'), '</button>']
  self.ui.SetState(['<div>', _('A button here: '), button, '</div>'])

Internationalized test argument
```````````````````````````````
Sometimes, test need to have arguments that accepts internationalized text. Use
:class:`~test.i18n.arg_utils.I18nArg` instead of
:class:`cros.factory.utils.arg_util.Arg` in this case.

User can pass a plain string, or a translation dict to the argument. The
argument in self.args is either ``None`` or a translation dict no matter what
the user passed in.

For example::

  from cros.factory.test.i18n import _
  from cros.factory.test.i18n import arg_utils as i18n_arg_utils
  from cros.factory.test import test_ui

  class MyTest(test_ui.TestCaseWithUI):
    ARGS = [
      i18n_arg_utils.I18nArg('text', 'Some text', default=_('Default text'))
    ]

    def setUp(self):
      self.ui.SetState(['text: ', self.args.text])

Manipulating i18n text
``````````````````````
There are several utility functions for transforming and combining translation
dict, for example::

  i18n.StringFormat('{a}[{b}]', a=1, b=_('Cancel'))
  # => {'en-US': '1[Cancel]', 'zh-CN': '1[取消]'}
  i18n.HTMLEscape({'en-US': '&<>', 'zh-CN': '&<>'})
  # => {'en-US': '&amp;&lt;&gt;', 'zh-CN': '&amp;&lt;&gt;'}

See `Method reference`_ for detail.

I18n in JavaScript
------------------
All literal strings that need to be translated should be passed as the first
argument of :func:`window._`.

The i18n API is under the namespace :js:class:`cros.factory.i18n`, and is
similar to Python API with three twists:

1. The method names start with lowercase letter. For example,
   :js:func:`cros.factory.i18n.stringFormat` instead of
   :js:func:`StringFormat`.
2. Since JavaScript doesn't kave keyword arguments, :js:func:`window._` support
   an additional argument of mapping from name to values. For example:

   .. code-block:: javascript

      _('Test {test}, run {id}', {test: _('some test'), id: 1})
3. Since there's no standarized "display" methods in JavaScript, two additional
   methods are introduced:

   * :js:func:`cros.factory.i18n.i18nLabel`, which takes a string or
     translation dict, and returns a :js:class:`goog.html.SafeHtml` from
     `closure library
     <https://google.github.io/closure-library/api/goog.html.SafeHtml.html>`_.
   * :js:func:`cros.factory.i18n.i18nLabelNode`, which takes a string or
     translation dict, and returns a :js:class:`Node` that can be inserted to
     document directly.

   Note that the first argument of these two functions do not need to be marked
   by :func:`window._`. For example:

   .. code-block:: javascript

      const div = document.getElementById('some-div')
      goog.dom.safe.setInnerHtml(cros.factory.i18n.i18nLabel('some text'))
      goog.dom.safe.appendChild(cros.factory.i18n.i18nLabelNode('other text'))
      goog.dom.safe.appendChild(
          cros.factory.i18n.i18nLabelNode(
              _('Test {test}, run {id}', {test: _('some test'), id: 1})))

I18n in static HTML
-------------------
Use ``<i18n-label>`` for text element that need to be translated. The
``i18n-label`` is a custom HTML tag that acts like a span, and styles can be
applied on it like a span. For example:

.. code-block:: html

  <i18n-label id="some-label" style="color: red">Some red text</i18n-label>

would show a red text according to current selected language.

Note that all continuous space characters inside the tag would be replaced by
one space, and leading / trailing spaces are removed, so the following two
snippets are equivalent:

.. code-block:: html

  <i18n-label>I am some text</i18n-label>

.. code-block:: html

  <i18n-label>
    I am
    some
    text
  </i18n-label>

I18n in JSON test list
----------------------
All string in either ``label`` or ``args`` can be prefixed by ``"i18n! "`` to
make it an internationalized text. Those string would be extracted to po files
automatically, and pytest can use :class:`I18nArg` to handle this kind of
argument. See `Internationalized test argument`_ for detail.

Example:

.. code-block:: json

  {
    "definitions": {
      "MyTest": {
        "pytest_name": "my_test",
        "label": "i18n! My Special Test",
        "args": {
          "text": "i18n! I'm an argument!",
          "other_arg": {
            "something": ["i18n! Transform is done recursively like eval!."]
          }
        }
      }
    }
  }

Since the translation dict is a normal :class:`dict`, a dict can be passed
directly from JSON. This is not advised since this makes it much harder to
modify translation or add new locale support, but can be useful when developing
or debugging. For example:

.. code-block:: json

  {
    "label": {
      "en-US": "Inline translation dict. Don't do this except for debugging!",
      "zh-CN": "..."
    }
  }

Manage translation files
------------------------
See
`Localization for ChromeOS Factory Software
<https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/po/README.md>`_
for detail on how to update or add .po files.

Method reference
----------------
.. autodata:: cros.factory.test.i18n.translation.DEFAULT_LOCALE

.. py:module:: cros.factory.test.i18n

.. autofunction:: _
.. autofunction:: Translated
.. autofunction:: StringFormat
.. autofunction:: NoTranslation
.. autofunction:: Translation
.. autofunction:: HTMLEscape

.. py:module:: cros.factory.test.i18n.arg_utils

.. autofunction:: I18nArg(name, help_msg, default=_DEFAULT_NOT_SET)
