This directory contains scripts to migrate Umpire environment.

For example, `0005.py` performs the Umpire environment migration from version 4
to version 5.

The migration scripts should be as independent as possible. Using constants or
calling methods from other module like `umpire_env` should be avoided because
those constants or methods might be changed in the future.
