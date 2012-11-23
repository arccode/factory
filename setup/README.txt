Factory setup scripts

This folder contains scripts for factory flow setup. All scripts here may be
executed in different environments:

 - Inside chroot of cros_sdk
 - Outside chroot but still with complete source tree
 - Inside a factory bundle running on arbitrary Linux device

So all scripts must use only the libraries in same folder and not relying on any
files in cros source tree (except chromeos-common.sh).
