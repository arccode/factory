# CrOS Factory: Init system

The `init` folder contains configurations to change ChromeOS boot flow into
factory-ready environment.

The goal is to start UI (Chrome) in Kiosk mode, and browsing factory web UI
port on default. And the real flow is:

1. This folder should be copied into `/mnt/stateful_partition` as path
   `dev_image/factory/init`, and mounted at `/usr/local/factory/init`.

2. `/etc/init/factory-preinit.conf` must be executed when *stopping*
   `startup.conf` (before `boot-service.conf` and UI are started). It will
   check factory mode at the beginning, then call
   `factory/init/startup preinit`, and then start `factory-init.conf`.

3. `/etc/init/factory-init.conf` must be executed right after
   `factory-preinit.conf` and before `boot-services.conf`. It will call
   `factory/init/startup init`. People can assume all jobs required by
   `boot-services.conf` are already done. It should be the critical section of
   boot flow. This is helpful for doing some actions which may cause side
   effect on upstart, e.g. reload upstart configuration.

4. `factory/init/startup init` will deal with the installation request (if
   exists) first. The script probes the request file called `install` in the
   same directory, if it exists and is not empty, the script reads the content
   from the request file (should be a path pointing to the factory toolkit
   file) and install the factory toolkit.
   See [Delayed Installation](#delayed-installation) for more info.

5. `factory/init/startup` will apply any rules in its sub folders, for example,
   binding a customized `/etc/chrome_dev.conf` (which will be parsed by Chrome
   session manager and applied for startup in `ui.conf`).

6. When `factory.conf` starts, it will invoke `factory/init/startup main`
   which loads rules from `main.d`. By default, this should start Goofy UI, but
   it may also be customized to start other services like Whale.

Now, when everything is set, we will have a new and unified boot flow:

    (upstart) startup -> [chromeos_startup] ->
    (upstart) factory-preinit -> [check is_factory_mode] ->
    [factory/init/startup preinit] -> [emit factory-init-event] ->
    (upstart) factory-init -> [factory/init/startup init] ->
    (upstart) boot_services ->
    (upstart) factory -> [factory/init/startup main] -> [goofy_control start] ->
    (upstart) ui (Chrome) -> [goofy] ->
    [emit login-prompt-visible] -> (upstart) other system services ...

And when developers run `factory_restart`, it brings up these services in same
flow (first factory then chrome).

See `main.d/README.md` for more information of how to add (also enable or
disable) new rules into each stage.

 - `preinit.d`: Rules applied on all systems at factory pre-initialization
   stage.
 - `init.d`: Rules applied on all systems at factory initialization stage.
 - `iptables.d`: Rules applied for network setup.
 - `goofy.d`: Rules applied according to factory configuration.
 - `main.d`: Rules applied for factory main service (`factory.conf`).


## Delayed Installation {#delayed-installation}

During the reimaging stage, the DUT downloads a test image and a factory toolkit
to the local storage. The DUT is responsible for installing the toolkit itself
afterward. But in that stage, the DUT (running factory shim or factory netboot
installer) lacks of `python` to finish essential works for installing the
factory toolkit. It can only extract the toolkit file but not install. We have
to delay this work until the first boot using test image environment.

This is the reason we must deal with the install request at the beginning of the
`init` process.
