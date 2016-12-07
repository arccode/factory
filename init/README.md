# CrOS Factory: Init system

The init folder contains configurations to change ChromeOS boot flow into
factory-ready environment.

The goal is to start UI (Chrome) in Kiosk mode, and browsing factory web UI
port on default. And the real flow is:

1. This folder should be copied into `/mnt/stateful_partition` as path
   `dev_image/factory/init`, and mounted at `/usr/local/factory/init`.

2. `/etc/init/factory-init.conf` must be executed when *starting*
   `boot-services.conf` (before UI is started), then calls
   `factory/init/startup`.

3. `factory/init/startup` will deal with the install request (if exists) first.
   The script probes the request file called `install` in the same directory, if
   it exists and is not empty, the script reads the content from the request
   file (should be a path pointing to the factory toolkit file) and install the
   factory toolkit. See [Delayed Installation](#delayed-installation) for more
   info.

4. `factory/init/startup` will apply any rules in its sub folders, for example,
   binding a customized `/etc/chrome_dev.conf` (which will be parsed by Chrome
   session manager and applied for startup in `ui.conf`).

5. When `factory.conf` starts, it will invoke `factory/init/startup main`
   which loads rules from `main.d`. By default this should start Goofy UI, but
   it may also be customized to start other services like Whale.

Now, when everything is set, we will have a new and unified boot flow:

    (upstart) startup -> [chromeos_startup] -> (upstart) boot_services ->
    (upstart) factory-init -> [factory/init/startup init] ->
    (upstart) factory -> [factory/init/startup main] -> [goofy_control start] ->
    (upstart) ui (Chrome) -> [goofy] ->
    [emit login-prompt-visible] -> (upstart) other system services ...

And when developers run factory_restart, it brings up these services in same
flow (first factory then chrome).

See `main.d/README.md` for more information of how to add (also enable or
disable) new rules into each stage.

 - `common.d`: Rules applied on all systems in system init.
 - `iptables.d`: Rules applied for network setup.
 - `goofy.d`: Rules applied according to factory configuration (run presenter,
   device, or monolithic mode).
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
