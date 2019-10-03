Chrome OS Factory Software Utilities
====================================
This directory contains utils that are designed to be portable for
use both inside and outside of `cros.factory` code.

For factory code, utils should be imported under the usual
namespace:

    from cros.factory.utils import file_utils

For non-factory code located in this repository, suggested use is
to create a symlink of the entire `utils` directory, or symlink
individual files.

    # cd my_project
    # mkdir utils
    # touch utils/__init__.py  # needed to mark utils as package
    # ln -s ../path/to/utils/file_utils.py file_utils.py
    from utils import file_utils

However, importing any utils module without being contained in a
package namespace will fail:

    # cd py/utils
    import file_utils  # WILL FAIL
    from file_utils import TouchFile  # WILL FAIL

    # cd my_project
    # ln -s ../path/to/utils/file_utils.py file_utils.py
    import file_utils  # WILL FAIL
