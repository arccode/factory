Migration tool for i18n test list changes.
==========================================

This tool would change some usage of old label_en and label_zh to use new i18n
library.

Usage
-----
Install yapf first (by `pip install yapf`),
then run `main.py -b {board}`.

The commands **don't** have to be run in chroot.

Caveats
-------
After the script is run, please check the following:

1. The automated added import lines may not be correctly sorted.
   Please sort them according to module's full path.

2. The code format may not be completely correct.
   It's done by yapf using Chromium style, but formatters can't handle the case
   of too long strings literal.

3. Check if there's any line marked as `#, fuzzy` in the generated .po file.
   Check if the translation is correct,
   and remove the `#, fuzzy` line after that.

4. Check the script's output to see if there's a section beginning with
   `Warnings/messages while refactoring:`.
   If the section exists, there are some labels that can't be automatically
   transformed.

   The most probable cause is that there are some test list of format like:
   ```
   OperatorTest(
       id='Barrier' + str(id_suffix),
       label_zh=u'检查关卡' + str(id_suffix),
       ...)
   ```
   This needs to be manually changed to:
   ```
   OperatorTest(
       id='Barrier' + str(id_suffix),
       label=i18n.StringFormat(_('Barrier{id_suffix}'), id_suffix=id_suffix),
       ...)
   ```
   And add following import if necessary:
   ```
   from cros.factory.test import i18n
   from cros.factory.test.i18n import _
   ```
   Then run `BOARD=${board} LOCALE=zh-CN make update` in `po` directory in
   public repository.

   Then edit `po/zh-CN.po` file inside board overlay, find the lines:
   ```
   msgid "Barrier{id_suffix}"
   msgstr ""
   ```
   and add the translation inside the `msgstr`.
   You should run `BOARD=${board} LOCALE=zh-CN make update` again after
   edit to make sure the formatting of .po file is consistent.
