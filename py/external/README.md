ChromeOS Factory Software External Modules
==========================================

This package folder provides a wrapper for loading external modules.

To make factory software more portable we want to virtualize the loading of
modules, allowing particular module to be loaded only-if-exists, or providing
a simplified implementation when the huge package is not available (for
instance, numpy).

For most modules you just need to create a symlink with right module name and
import it from `cros.factory`. Examples:

    from cros.factory.external import cv

Then use `cv` as usual.


To check if a module was really loaded, check `module.MODULE_READY` variable.

To debug module import issue (i.e., abort when import failed), set environment
variable `DEBUG_IMPORT` and run again.

If you need to use a module in import stage (i.e., inheriting some class inside
the module), then you also have to provide a dummy implementation in `_dummy`
folder.
