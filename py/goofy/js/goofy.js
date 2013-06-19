// Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.Goofy');

goog.require('goog.crypt');
goog.require('goog.crypt.base64');
goog.require('goog.crypt.Sha1');
goog.require('goog.date.Date');
goog.require('goog.date.DateTime');
goog.require('goog.debug.ErrorHandler');
goog.require('goog.debug.FancyWindow');
goog.require('goog.debug.Logger');
goog.require('goog.dom');
goog.require('goog.dom.classes');
goog.require('goog.dom.iframe');
goog.require('goog.events');
goog.require('goog.events.EventHandler');
goog.require('goog.events.KeyCodes');
goog.require('goog.i18n.DateTimeFormat');
goog.require('goog.i18n.NumberFormat');
goog.require('goog.json');
goog.require('goog.math');
goog.require('goog.net.WebSocket');
goog.require('goog.net.XhrIo');
goog.require('goog.string');
goog.require('goog.style');
goog.require('goog.Uri');
goog.require('goog.ui.AdvancedTooltip');
goog.require('goog.ui.Checkbox');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');
goog.require('goog.ui.MenuSeparator');
goog.require('goog.ui.PopupMenu');
goog.require('goog.ui.ProgressBar');
goog.require('goog.ui.Prompt');
goog.require('goog.ui.Select');
goog.require('goog.ui.SplitPane');
goog.require('goog.ui.SubMenu');
goog.require('goog.ui.tree.TreeControl');
goog.require('goog.window');

cros.factory.logger = goog.debug.Logger.getLogger('cros.factory');

/**
 * @define {boolean} Whether to automatically collapse items once tests have
 *     completed.
 */
cros.factory.AUTO_COLLAPSE = false;

/**
 * Keep-alive interval for the WebSocket.  (Chrome times out
 * WebSockets every ~1 min, so 30 s seems like a good interval.)
 * @const
 * @type number
 */
cros.factory.KEEP_ALIVE_INTERVAL_MSEC = 30000;

/**
 * Interval at which to update system status.
 * @const
 * @type number
 */
cros.factory.SYSTEM_STATUS_INTERVAL_MSEC = 5000;

/**
 * Interval at which to try mounting the USB drive.
 * @const
 * @type number
 */
cros.factory.MOUNT_USB_DELAY_MSEC = 1000;

/**
 * Width of the control panel, as a fraction of the viewport size.
 * @type number
 */
cros.factory.CONTROL_PANEL_WIDTH_FRACTION = 0.2;

/**
 * Minimum width of the control panel, in pixels.
 * @type number
 */
cros.factory.CONTROL_PANEL_MIN_WIDTH = 275;

/**
 * Height of the log pane, as a fraction of the viewport size.
 * @type number
 */
cros.factory.LOG_PANE_HEIGHT_FRACTION = 0.2;

/**
 * Minimum height of the log pane, in pixels.
 * @type number
 */
cros.factory.LOG_PANE_MIN_HEIGHT = 170;

/**
 * Maximum size of a dialog (width or height) as a fraction of viewport size.
 * @type number
 */
cros.factory.MAX_DIALOG_SIZE_FRACTION = 0.75;

/**
 * Hover delay for a non-failing test.
 * @type number
 */
cros.factory.NON_FAILING_TEST_HOVER_DELAY_MSEC = 250;

/**
 * Makes a label that displays English (or optionally Chinese).
 * @param {string} en
 * @param {string=} zh
 */
cros.factory.Label = function(en, zh) {
    return '<span class="goofy-label-en">' + en + '</span>' +
      '<span class="goofy-label-zh">' + (zh || en) + '</span>';
};

/**
 * Makes control content that displays English (or optionally Chinese).
 *
 * Note that this actually returns a Node, but we call it an unknown
 * type so it will be accepted by various buggy methods such as
 * goog.ui.Dialog.setTitle.
 *
 * @param {string} en
 * @param {string=} zh
 * @return {?}
 */
cros.factory.Content = function(en, zh) {
    var span = document.createElement('span');
    span.innerHTML = cros.factory.Label(en, zh);
    return span;
};

/**
 * Labels for items in system info.
 * @type Array.<Object.<string, string>>
 */
cros.factory.SYSTEM_INFO_LABELS = [
    {key: 'mlb_serial_number', label: cros.factory.Label('MLB Serial Number')},
    {key: 'serial_number', label: cros.factory.Label('Serial Number')},
    {key: 'factory_image_version',
     label: cros.factory.Label('Factory Image Version')},
    {key: 'wlan0_mac', label: cros.factory.Label('WLAN MAC')},
    {key: 'ips', label: cros.factory.Label('IP Addresses')},
    {key: 'kernel_version', label: cros.factory.Label('Kernel')},
    {key: 'architecture', label: cros.factory.Label('Architecture')},
    {key: 'ec_version', label: cros.factory.Label('EC')},
    {key: 'firmware_version', label: cros.factory.Label('Firmware')},
    {key: 'root_device', label: cros.factory.Label('Root Device')},
    {key: 'factory_md5sum', label: cros.factory.Label('Factory MD5SUM'),
     transform: function(value) {
            return value || cros.factory.Label('(no update)');
        }}
                                   ];

cros.factory.UNKNOWN_LABEL = '<span class="goofy-unknown">' +
    cros.factory.Label('Unknown') + '</span>';

/**
 * An item in the test list.
 * @typedef {{path: string, label_en: string, label_zh: string,
 *            kbd_shortcut: string, subtests: Array, disable_abort: boolean}}
 */
cros.factory.TestListEntry;

/**
 * A pending shutdown event.
 * @typedef {{delay_secs: number, time: number, operation: string,
 *            iteration: number, iterations: number }}
 */
cros.factory.PendingShutdownEvent;

/**
 * Entry in test history returned by get_test_history.
 * @typedef {{init_time: number, end_time: number, status: string,
 *            path: string, invocation: string}}
 */
cros.factory.HistoryMetadata;

/**
 * Entry in test history.
 * @typedef {{metadata: cros.factory.HistoryMetadata, log: string}}
 */
cros.factory.HistoryEntry;

/**
 * TestState object in an event or RPC response.
 * @typedef {{status: string, skip: boolean, visible: boolean}}
 */
cros.factory.TestState;

/**
 * Information about a test list.
 * @typedef {{id: string, name: string, enabled: boolean}}
 */
cros.factory.TestListInfo;

/**
 * Public API for tests.
 * @constructor
 * @param {cros.factory.Invocation} invocation
 */
cros.factory.Test = function(invocation) {
    /**
     * @type cros.factory.Invocation
     */
    this.invocation = invocation;

    /**
     * Map of char codes to handlers.  Null if not yet initialized.
     * @type {?Object.<number, function()>}
     */
    this.keyHandlers = null;
};

/**
 * Passes the test.
 * @export
 */
cros.factory.Test.prototype.pass = function() {
    this.invocation.goofy.sendEvent(
        'goofy:end_test', {
            'status': 'PASSED',
            'invocation': this.invocation.uuid,
            'test': this.invocation.path
        });
    this.invocation.dispose();
};

/**
 * Fails the test with the given error message.
 * @export
 * @param {string} errorMsg
 */
cros.factory.Test.prototype.fail = function(errorMsg) {
    this.invocation.goofy.sendEvent('goofy:end_test', {
            'status': 'FAILED',
            'error_msg': errorMsg,
            'invocation': this.invocation.uuid,
            'test': this.invocation.path
        });
    this.invocation.dispose();
};

/**
 * Sends an event to the test backend.
 * @export
 * @param {string} subtype the event type
 * @param {string} data the event data
 */
cros.factory.Test.prototype.sendTestEvent = function(subtype, data) {
    this.invocation.goofy.sendEvent('goofy:test_ui_event', {
        'test': this.invocation.path,
        'invocation': this.invocation.uuid,
        'subtype': subtype,
        'data': data
        });
};

/**
 * Binds a key to a handler.
 * @param {number} keyCode the key code to bind.
 * @param {function()} handler the function to call when the key is pressed.
 * @export
 */
cros.factory.Test.prototype.bindKey = function(keyCode, handler) {
    if (!this.keyHandlers) {
        this.keyHandlers = new Object();
        // Set up the listener.
        goog.events.listen(
            this.invocation.iframe.contentWindow,
            goog.events.EventType.KEYUP,
            function(event) {
                handler = this.keyHandlers[event.keyCode];
                if (handler) {
                    handler();
                }
            }, false, this);
    }
    this.keyHandlers[keyCode] = handler;
};

/**
 * Unbinds a key and removes its handler.
 * @param {number} keyCode the key code to unbind.
 * @export
 */
cros.factory.Test.prototype.unbindKey = function(keyCode) {
    if (this.keyHandlers && keyCode in this.keyHandlers) {
        delete this.keyHandlers[keyCode];
    }
}

/**
 * Triggers an update check.
 */
cros.factory.Test.prototype.updateFactory = function() {
    this.invocation.goofy.updateFactory();
};

/**
 * Sets iframe to fullscreen size. Also iframe gets higher z-index than
 * test panel so it will cover all other stuffs in goofy.
 * @export
 * @param {boolean} enable fullscreen iframe or not.
 */
cros.factory.Test.prototype.setFullScreen = function(enable) {
    goog.dom.classes.enable(this.invocation.iframe, 'goofy-test-fullscreen',
                            enable);
};

/**
 * UI for a single test invocation.
 * @constructor
 * @param {cros.factory.Goofy} goofy
 * @param {string} path
 */
cros.factory.Invocation = function(goofy, path, uuid) {
    /**
     * Reference to the Goofy object.
     * @type cros.factory.Goofy
     */
    this.goofy = goofy;

    /**
     * @type string
     */
    this.path = path;

    /**
     * UUID of the invocation.
     * @type string
     */
    this.uuid = uuid;

    /**
     * Test API for the invocation.
     */
    this.test = new cros.factory.Test(this);

    /**
     * The iframe containing the test.
     * @type HTMLIFrameElement
     */
    this.iframe = goog.dom.iframe.createBlank(new goog.dom.DomHelper(document));
    goog.dom.classes.add(this.iframe, 'goofy-test-iframe');
    goog.dom.classes.enable(this.iframe, 'goofy-test-visible',
                            /** @type boolean */(
                                goofy.pathTestMap[path].state.visible));
    document.getElementById('goofy-main').appendChild(this.iframe);
    this.iframe.contentWindow.$ = goog.bind(function(id) {
        return this.iframe.contentDocument.getElementById(id);
    }, this);
    this.iframe.contentWindow.test = this.test;
    this.iframe.contentWindow.focus();
};

/**
 * Returns state information for this invocation.
 * @return Object
 */
cros.factory.Invocation.prototype.getState = function() {
    return this.goofy.pathTestMap[this.path].state;
};

/**
 * Disposes of the invocation (and destroys the iframe).
 */
cros.factory.Invocation.prototype.dispose = function() {
    if (this.iframe) {
        goog.dom.removeNode(this.iframe);
        this.goofy.invocations[this.uuid] = null;
        this.iframe = null;
    }
};

/**
 * Types of notes.
 * @type Array.<string, string>
 */
cros.factory.NOTE_LEVEL = [
    {'name': 'INFO', 'message': 'Informative message only'},
    {'name': 'WARNING','message': 'Displays a warning icon'},
    {'name': 'CRITICAL', 'message': 'Testing is stopped indefinitely'}];

/**
 * Constructor for Note.
 * @constructor
 * @param {string} name
 * @param {string} text
 * @param {string} timestamp
 * @param {string} level
 */
cros.factory.Note = function(name, text, timestamp, level) {
    this.name = name;
    this.text = text;
    this.timestamp = timestamp;
    this.level = level;
}

/**
 * UI for displaying critical factory notes.
 * @constructor
 * @param {Array.<cros.factory.Note>} notes
 */
cros.factory.CriticalNoteDisplay = function(goofy, notes) {
    this.goofy = goofy;
    this.div = goog.dom.createDom('div', 'goofy-fullnote-display-outer');
    document.getElementById('goofy-main').appendChild(this.div);

    var innerDiv = goog.dom.createDom('div', 'goofy-fullnote-display-inner');
    this.div.appendChild(innerDiv);

    var titleDiv = goog.dom.createDom('div', 'goofy-fullnote-title');
    var titleImg = goog.dom.createDom('img', {'class': 'goofy-fullnote-logo',
                                              'src': 'images/warning.svg'});
    titleDiv.appendChild(titleImg);
    titleDiv.appendChild(cros.factory.Content('Factory tests stopped',
                                              '工厂测试已停止'));
    innerDiv.appendChild(titleDiv);

    var noteDiv = goog.dom.createDom('div', 'goofy-fullnote-note');
    noteDiv.innerHTML = this.goofy.getNotesView();
    innerDiv.appendChild(noteDiv);
};

/**
 * Disposes of the critical factory notes display.
 */
cros.factory.CriticalNoteDisplay.prototype.dispose = function() {
    if (this.div) {
        goog.dom.removeNode(this.div);
        this.div = null;
    }
};

/**
 * The main Goofy UI.
 *
 * @constructor
 */
cros.factory.Goofy = function() {
    /**
     * The WebSocket we'll use to communicate with the backend.
     * @type goog.net.WebSocket
     */
    this.ws = new goog.net.WebSocket();

    /**
     * Whether we have opened the WebSocket yet.
     * @type boolean
     */
    this.wsOpened = false;

    /**
     * The UUID that we received from Goofy when starting up.
     * @type {?string}
     */
    this.uuid = null;

    /**
     * The currently visible context menu, if any.
     * @type goog.ui.PopupMenu
     */
    this.contextMenu = null;

    /**
     * The last test for which a context menu was displayed.
     * @type {?string}
     */
    this.lastContextMenuPath = null;

    /**
     * The time at which the last context menu was hidden.
     * @type {?number}
     */
    this.lastContextMenuHideTime = null;

    /**
     * All tooltips that we have created.
     * @type Array.<goog.ui.AdvancedTooltip>
     */
    this.tooltips = [];

    /**
     * The test tree.
     */
    this.testTree = new goog.ui.tree.TreeControl('Tests');
    this.testTree.setShowRootNode(false);
    this.testTree.setShowLines(false);

    /**
     * A map from test path to the tree node for each test.
     * @type Object.<string, goog.ui.tree.BaseNode>
     */
    this.pathNodeMap = new Object();

    /**
     * A map from test path to the entry in the test list for that test.
     * @type Object.<string, cros.factory.TestListEntry>
     */
    this.pathTestMap = new Object();


    /**
     * A map from test path to the tree node html id for external reference.
     * @type Object.<string, string>
     */
    this.pathNodeIdMap = new Object();

    /**
     * Whether Chinese mode is currently enabled.
     *
     * TODO(jsalz): Generalize this to multiple languages (but this isn't
     * really necessary now).
     *
     * @type boolean
     */
    this.zhMode = false;

    /**
     * The tooltip for version number information.
     */
    this.infoTooltip = new goog.ui.AdvancedTooltip(
        document.getElementById('goofy-system-info-hover'));
    this.infoTooltip.setHtml('Version information not yet available.');

    /**
     * UIs for individual test invocations (by UUID).
     * @type Object.<string, cros.factory.Invocation>
     */
    this.invocations = {};

    /**
     * Eng mode prompt.
     * @type goog.ui.Dialog
     */
    this.engineeringModeDialog = null;

    /**
     * Shutdown prompt dialog.
     * @type goog.ui.Dialog
     */
    this.shutdownDialog = null;

    /**
     * Visible dialogs.
     * @type Array.<goog.ui.Dialog>
     */
    this.dialogs = [];

    /**
     * Whether eng mode is enabled.
     * @type {boolean}
     */
    this.engineeringMode = false;

    /**
     * Last system info received.
     * @type Object.<string, Object>
     */
    this.systemInfo = {};

    /**
     * SHA1 hash of password to take UI out of operator mode.  If
     * null, eng mode is always enabled.  Defaults to an invalid '?',
     * which means that eng mode cannot be entered (will be set from
     * Goofy's shared_data).
     * @type {?string}
     */
    this.engineeringPasswordSHA1 = '?';

    /**
     * Debug window.
     * @type {goog.debug.FancyWindow}
     */
    this.debugWindow = new goog.debug.FancyWindow('main');
    this.debugWindow.setEnabled(false);
    this.debugWindow.init();

    /**
     * Key listener bound to this object.
     */
    this.boundKeyListener = goog.bind(this.keyListener, this);

    /**
     * Various tests lists that can be enabled in engineering mode.
     * @type Array.<cros.factory.TestListInfo>
     */
    this.testLists = [];

    // Set up magic keyboard shortcuts.
    goog.events.listen(
        window, goog.events.EventType.KEYDOWN, this.keyListener, true, this);
};

/**
 * Sets the title of a modal dialog as HTML.
 * @param {string} titleHTML
 */
cros.factory.Goofy.setDialogTitleHTML = function(dialog, titleHTML) {
    goog.dom.getElementByClass(
        'modal-dialog-title-text', dialog.getElement()).innerHTML = titleHTML;
};

/**
 * Event listener for Ctrl-Alt-keypress.
 * @param {goog.events.KeyEvent} event
 */
cros.factory.Goofy.prototype.keyListener = function(event) {
    if (event.altKey && event.ctrlKey) {
        switch (String.fromCharCode(event.keyCode)) {
        case '0':
            if (!this.dialogs.length) {  // If no dialogs are shown yet
                this.promptEngineeringPassword();
            }
            break;
        case '1':
            this.debugWindow.setEnabled(true);
            break;
        default:
            // Nothing
        }
    }
    // Disable shortcut Ctrl-Alt-* when not in engineering mode.
    // Note: platformModifierKey == Command-key for Mac browser;
    //     for non-Mac browsers, it is Ctrl-key.
    if (!this.engineeringMode &&
        event.altKey && event.platformModifierKey) {
        event.stopPropagation();
        event.preventDefault();
    }
};

/**
 * Initializes the split panes.
 */
cros.factory.Goofy.prototype.initSplitPanes = function() {
    var viewportSize = goog.dom.getViewportSize(goog.dom.getWindow(document));
    var mainComponent = new goog.ui.Component();
    var consoleComponent = new goog.ui.Component();
    var mainAndConsole = new goog.ui.SplitPane(
        mainComponent, consoleComponent,
        goog.ui.SplitPane.Orientation.VERTICAL);
    mainAndConsole.setInitialSize(
        viewportSize.height -
        Math.max(cros.factory.LOG_PANE_MIN_HEIGHT,
                 1 - cros.factory.LOG_PANE_HEIGHT_FRACTION));

    goog.debug.catchErrors(goog.bind(function(info) {
        try {
            this.logToConsole('JavaScript error (' + info.fileName +
                              ', line ' + info.line + '): ' + info.message,
                              'goofy-internal-error');
        } catch (e) {
            // Oof... error while logging an error!  Maybe the DOM
            // isn't set up properly yet; just ignore.
        }
    }, this), false);

    var controlComponent = new goog.ui.Component();
    var topSplitPane = new goog.ui.SplitPane(
        controlComponent, mainAndConsole,
        goog.ui.SplitPane.Orientation.HORIZONTAL);
    topSplitPane.setInitialSize(
        Math.max(cros.factory.CONTROL_PANEL_MIN_WIDTH,
                 viewportSize.width *
                 cros.factory.CONTROL_PANEL_WIDTH_FRACTION));
    // Decorate the uppermost splitpane and disable its context menu.
    var topSplitPaneElement = document.getElementById('goofy-splitpane');
    topSplitPane.decorate(topSplitPaneElement);
    // Disable context menu except in engineering mode.
    goog.events.listen(
        topSplitPaneElement, goog.events.EventType.CONTEXTMENU,
        function(event) {
            if (!this.engineeringMode) {
                event.stopPropagation();
                event.preventDefault();
            }
        },
        false, this);

    mainComponent.getElement().id = 'goofy-main';
    mainComponent.getElement().innerHTML = (
        '<img id="goofy-main-logo" src="images/logo256.png">');
    consoleComponent.getElement().id = 'goofy-console';
    this.console = consoleComponent.getElement();
    this.main = mainComponent.getElement();

    var propagate = true;
    goog.events.listen(
        topSplitPane, goog.ui.Component.EventType.CHANGE,
        function(event) {
            if (!propagate) {
                // Prevent infinite recursion
                return;
            }

            propagate = false;
            mainAndConsole.setFirstComponentSize(
                mainAndConsole.getFirstComponentSize());
            propagate = true;

            var rect = mainComponent.getElement().getBoundingClientRect();
            this.sendRpc('get_shared_data', ['ui_scale_factor'],
                         function(uiScaleFactor) {
                             this.sendRpc('set_shared_data',
                                          ['test_widget_size',
                                           [rect.width * uiScaleFactor,
                                            rect.height * uiScaleFactor],
                                           'test_widget_position',
                                           [rect.left * uiScaleFactor,
                                            rect.top * uiScaleFactor]]);
                         });
        }, false, this);
    mainAndConsole.setFirstComponentSize(
        mainAndConsole.getFirstComponentSize());
    goog.events.listen(
        window, goog.events.EventType.RESIZE,
        function(event) {
            topSplitPane.setSize(
                goog.dom.getViewportSize(goog.dom.getWindow(document) ||
                                         window));
        });

    // Whenever we get focus, try to focus any visible iframe (if no modal
    // dialog is visible).
    goog.events.listen(
        window, goog.events.EventType.FOCUS,
        function() { goog.Timer.callOnce(this.focusInvocation, 0, this); },
        false, this);
};

/**
 * Returns focus to any visible invocation.
 */
cros.factory.Goofy.prototype.focusInvocation = function() {
    if (goog.array.find(this.dialogs, function(dialog) {
                return dialog.isVisible();
            })) {
        // Don't divert focus, since a dialog is visible.
        return;
    }

    goog.object.forEach(this.invocations, function(i) {
            if (i && i.iframe && /** @type boolean */(
                    i.getState().visible)) {
                goog.Timer.callOnce(goog.bind(function() {
                    if (!this.contextMenu) {
                        i.iframe.focus();
                        i.iframe.contentWindow.focus();
                    }
                }, this));
            }
        }, this);
};

/**
 * Initializes the WebSocket.
 */
cros.factory.Goofy.prototype.initWebSocket = function() {
    goog.events.listen(this.ws, goog.net.WebSocket.EventType.OPENED,
                       function(event) {
                           this.logInternal('Connection to Goofy opened.');
                           this.wsOpened = true;
                       }, false, this);
    goog.events.listen(this.ws, goog.net.WebSocket.EventType.ERROR,
                       function(event) {
                           this.logInternal('Error connecting to Goofy.');
                       }, false, this);
    goog.events.listen(this.ws, goog.net.WebSocket.EventType.CLOSED,
                       function(event) {
                           if (this.wsOpened) {
                               this.logInternal('Connection to Goofy closed.');
                               this.wsOpened = false;
                           }
                       }, false, this);
    goog.events.listen(this.ws, goog.net.WebSocket.EventType.MESSAGE,
                       function(event) {
                           this.handleBackendEvent(event.message);
                       }, false, this);
    window.setInterval(goog.bind(this.keepAlive, this),
                       cros.factory.KEEP_ALIVE_INTERVAL_MSEC);
    window.setInterval(goog.bind(this.updateStatus, this),
                       cros.factory.SYSTEM_STATUS_INTERVAL_MSEC);
    this.updateStatus();
    this.ws.open("ws://" + window.location.host + "/event");
};

/**
 * Starts the UI.
 */
cros.factory.Goofy.prototype.init = function() {
    this.initLanguageSelector();
    this.initSplitPanes();

    // Listen for keyboard shortcuts.
    goog.events.listen(
        window, goog.events.EventType.KEYDOWN,
        function(event) {
            if (event.altKey || event.ctrlKey) {
                this.handleShortcut(String.fromCharCode(event.keyCode));
            }
        }, false, this);

    this.initWebSocket();
    this.sendRpc('GetTestLists', [], function(testLists) {
        this.testLists = testLists;
    });
    this.sendRpc('get_test_list', [], this.setTestList);
    this.sendRpc('get_shared_data', ['system_info'], this.setSystemInfo);
    this.sendRpc('get_shared_data', ['factory_note', true], this.updateNote);
    this.sendRpc(
        'get_shared_data', ['test_list_options'],
            function(options) {
                this.engineeringPasswordSHA1 =
                    options['engineering_password_sha1'];
                // If no password, enable eng mode, and don't
                // show the 'disable' link, since there is no way to
                // enable it.
                goog.style.showElement(document.getElementById(
                    'goofy-disable-engineering-mode'),
                    this.engineeringPasswordSHA1 != null);
                this.setEngineeringMode(this.engineeringPasswordSHA1 == null);
            });
    this.sendRpc(
        'get_shared_data', ['startup_error'],
        function(error) {
            this.alert(
                cros.factory.Label(
                    ('An error occurred while starting ' +
                     'the factory test system.<br>' +
                     'Factory testing cannot proceed.'),
                    ('开工厂测试系统时发生错误.<br>' +
                     '没办法继续测试.')) +
                    '<div class="goofy-startup-error">' +
                    goog.string.htmlEscape(error) +
                    '</div>');
        },
        function() {
            // Unable to retrieve the key; that's fine, no startup error!
        });

    var timer = new goog.Timer(1000);
    goog.events.listen(timer, goog.Timer.TICK, this.updateTime, false, this);
    timer.dispatchTick();
    timer.start();
};

/**
 * Sets up the language selector.
 */
cros.factory.Goofy.prototype.initLanguageSelector = function() {
    goog.events.listen(
        document.getElementById('goofy-language-selector'),
        goog.events.EventType.CLICK,
        function(event) {
            this.zhMode = !this.zhMode;
            this.updateCSSClasses();
            this.sendRpc('set_shared_data',
                         ['ui_lang', this.zhMode ? 'zh' : 'en']);
        }, false, this);

    this.updateCSSClasses();
    this.sendRpc('get_shared_data', ['ui_lang'], function(lang) {
            this.zhMode = lang == 'zh';
            this.updateCSSClasses();
        });
};

/**
 * Gets an invocation for a test (creating it if necessary).
 *
 * @param {string} path
 * @param {string} invocationUuid
 * @return the invocation, or null if the invocation has already been created
 *     and deleted.
 */
cros.factory.Goofy.prototype.getOrCreateInvocation = function(
    path, invocationUuid) {
    if (!(invocationUuid in this.invocations)) {
        cros.factory.logger.info('Creating UI for test ' + path +
                                 ' (invocation ' + invocationUuid);
        this.invocations[invocationUuid] =
            new cros.factory.Invocation(this, path, invocationUuid);
    }
    return this.invocations[invocationUuid];
};

/**
 * Updates language classes in a document based on the current value of
 * zhMode.
 */
cros.factory.Goofy.prototype.updateCSSClassesInDocument = function(doc) {
    if (doc.body) {
        goog.dom.classes.enable(doc.body, 'goofy-lang-en', !this.zhMode);
        goog.dom.classes.enable(doc.body, 'goofy-lang-zh', this.zhMode);
        goog.dom.classes.enable(doc.body, 'goofy-engineering-mode',
                                this.engineeringMode);
        goog.dom.classes.enable(doc.body, 'goofy-operator-mode',
                                !this.engineeringMode);
    }
};

/**
 * Updates language classes in the UI based on the current value of
 * zhMode.
 */
cros.factory.Goofy.prototype.updateCSSClasses = function() {
    this.updateCSSClassesInDocument.call(this, document);
    goog.object.forEach(this.invocations, function(i) {
        if (i && i.iframe) {
            this.updateCSSClassesInDocument.call(this,
                i.iframe.contentDocument);
        }
    }, this);
}

/**
 * Updates the system info tooltip.
 * @param systemInfo Object.<string, string>
 */
cros.factory.Goofy.prototype.setSystemInfo = function(systemInfo) {
    this.systemInfo = systemInfo;

    var table = [];
    table.push('<table id="goofy-system-info">');
    goog.array.forEach(cros.factory.SYSTEM_INFO_LABELS, function(item) {
            var value = systemInfo[item.key];
            var html;
            if (item.transform) {
                html = item.transform(value);
            } else {
                html = value == undefined ?
                    cros.factory.UNKNOWN_LABEL :
                    goog.string.htmlEscape(value);
            }
            table.push(
                       '<tr><th>' + item.label + '</th><td>' + html +
                       '</td></tr>');
        });
    table.push('<tr><th>' +
               cros.factory.Label('System time', '系统时间') +
               '</th><td id="goofy-time"></td></th></tr>');
    table.push('</table>');
    this.infoTooltip.setHtml(table.join(''));
    this.updateTime();

    goog.dom.classes.enable(document.body, 'goofy-update-available',
                            !!systemInfo['update_md5sum']);
};

/**
 * Updates notes.
 */
cros.factory.Goofy.prototype.updateNote = function(notes) {
    this.notes = notes;
    var currentLevel = notes ? notes[notes.length - 1].level : '';

    goog.array.forEach(cros.factory.NOTE_LEVEL, function(lvl) {
        goog.dom.classes.enable(document.getElementById('goofy-logo'),
                                'goofy-note-' + lvl['name'].toLowerCase(),
                                currentLevel == lvl['name']);
    });

    if (this.noteDisplay) {
        this.noteDisplay.dispose();
        this.noteDisplay = null;
    }

    if (notes && notes[notes.length - 1].level == 'CRITICAL') {
        this.noteDisplay =
            new cros.factory.CriticalNoteDisplay(this, notes);
    }
};

cros.factory.Goofy.prototype.MDHMS_TIME_FORMAT =
    new goog.i18n.DateTimeFormat('MM/dd HH:mm:ss');
/**
 * Gets factory notes list.
 */
cros.factory.Goofy.prototype.getNotesView = function() {
    var table = [];
    table.push('<table id="goofy-note-list">');
    goog.array.forEachRight(this.notes, function(item) {
        var d = new Date(0);
        d.setUTCSeconds(item.timestamp);
        table.push('<tr><td class="goofy-note-time">' +
                   this.MDHMS_TIME_FORMAT.format(d) +
                   '</td><th class="goofy-note-name">' +
                   goog.string.htmlEscape(item.name) +
                   '</th><td class="goofy-note-text">' +
                   goog.string.htmlEscape(item.text) +
                   '</td></tr>');
    }, this);
    table.push('</table>');
    return table.join('');
};

/**
 * Displays a dialog of notes.
 */
cros.factory.Goofy.prototype.viewNotes = function() {
    if (!this.notes)
        return;

    var dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    dialog.setModal(false);

    var viewSize = goog.dom.getViewportSize(
        goog.dom.getWindow(document) || window);
    var maxWidth = viewSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
    var maxHeight = viewSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;

    dialog.setContent('<div class="goofy-note-container" style="max-width: ' +
                      maxWidth + '; max-height: ' + maxHeight + '">' +
                      this.getNotesView() + '</div>');
    dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
    dialog.setVisible(true);
    cros.factory.Goofy.setDialogTitleHTML(dialog, 'Factory Notes');
};

/**
 * Updates the current time.
 */
cros.factory.Goofy.prototype.updateTime = function() {
    var element = document.getElementById('goofy-time');
    if (element) {
        element.innerHTML = new goog.date.DateTime().toUTCIsoString(true) +
            ' UTC';
    }
};

/**
 * Registers a dialog.  sets the dialog setDisposeOnHide to true, and
 * returns focus to any running invocation when the dialog is
 * hidden/disposed.
 *
 * @param {goog.ui.Dialog} dialog
 */
cros.factory.Goofy.prototype.registerDialog = function(dialog) {
    this.dialogs.push(dialog);
    dialog.setDisposeOnHide(true);
    goog.events.listen(dialog, goog.ui.Component.EventType.SHOW, function() {
            window.focus();
            // Hack: if the dialog contains an input element or
            // button, focus it.  (For instance, Prompt only calls
            // select(), not focus(), on the text field, which causes
            // ESC and Enter shortcuts not to work.)
            var elt = dialog.getElement();
            var inputs = elt.getElementsByTagName('input');
            if (!inputs.length) {
                inputs = elt.getElementsByTagName('button');
            }
            if (inputs.length) {
                inputs[0].focus();
            }
        }, false, this);
    goog.events.listen(dialog, goog.ui.Component.EventType.HIDE, function() {
            goog.Timer.callOnce(this.focusInvocation, 0, this);
            goog.array.remove(this.dialogs, dialog);
        }, false, this);
};

/**
 * Displays an alert.
 * @param {string} messageHtml
 */
cros.factory.Goofy.prototype.alert = function(messageHtml) {
    var dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    dialog.setTitle('Alert');
    dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
    dialog.setContent(messageHtml);
    dialog.setVisible(true);
    goog.dom.classes.add(dialog.getElement(), 'goofy-alert');
};

/**
 * Centers an element over the console.
 * @param {Element} element
 */
cros.factory.Goofy.prototype.positionOverConsole = function(element) {
    var consoleBounds = goog.style.getBounds(this.console.parentNode);
    var size = goog.style.getSize(element);
    goog.style.setPosition(
        element,
        consoleBounds.left + consoleBounds.width/2 - size.width/2,
        consoleBounds.top + consoleBounds.height/2 - size.height/2);
};

/**
 * Prompts to enter eng mode.
 */
cros.factory.Goofy.prototype.promptEngineeringPassword = function() {
    if (this.engineeringModeDialog) {
        this.engineeringModeDialog.setVisible(false);
        this.engineeringModeDialog.dispose();
        this.engineeringModeDialog = null;
    }
    if (!this.engineeringPasswordSHA1) {
        this.alert('No password has been set.');
        return;
    }
    if (this.engineeringMode) {
        this.setEngineeringMode(false);
        return;
    }

    this.engineeringModeDialog = new goog.ui.Prompt(
        'Password', '',
        goog.bind(function(text) {
            if (!text || text == '') {
                return;
            }
            var hash = new goog.crypt.Sha1();
            hash.update(text);
            var digest = goog.crypt.byteArrayToHex(hash.digest());
            if (digest == this.engineeringPasswordSHA1) {
                this.setEngineeringMode(true);
            } else {
                this.alert('Incorrect password.');
            }
        }, this));
    this.registerDialog(this.engineeringModeDialog);
    this.engineeringModeDialog.setVisible(true);
    goog.dom.classes.add(this.engineeringModeDialog.getElement(),
                         'goofy-engineering-mode-dialog');
    this.engineeringModeDialog.reposition();
    this.positionOverConsole(this.engineeringModeDialog.getElement());
};

/**
 * Sets eng mode.
 * @param {boolean} enabled
 */
cros.factory.Goofy.prototype.setEngineeringMode = function(enabled) {
    this.engineeringMode = enabled;
    this.updateCSSClasses();
    this.sendRpc('set_shared_data', ['engineering_mode', enabled]);
};

/**
 * Deals with data about a pending reboot.
 * @param {cros.factory.PendingShutdownEvent} shutdownInfo
 */
cros.factory.Goofy.prototype.setPendingShutdown = function(shutdownInfo) {
    if (this.shutdownDialog) {
        this.shutdownDialog.setVisible(false);
        this.shutdownDialog.dispose();
        this.shutdownDialog = null;
    }
    if (!shutdownInfo || !shutdownInfo.time) {
        return;
    }

    var verbEn = shutdownInfo.operation == 'reboot' ?
        'Rebooting' : 'Shutting down';
    var verbZh = shutdownInfo.operation == 'reboot' ? '重开机' : '关机';

    var timesEn = shutdownInfo.iterations == 1 ? 'once' : (
        shutdownInfo.iteration + ' of ' + shutdownInfo.iterations + ' times');
    var timesZh = shutdownInfo.iterations == 1 ? '1次' : (
        shutdownInfo.iterations + '次' + verbZh + '测试中的第' +
        shutdownInfo.iteration + '次');

    this.shutdownDialog = new goog.ui.Dialog();
    this.registerDialog(this.shutdownDialog);
    this.shutdownDialog.setContent(
        '<p>' + verbEn + ' in <span class="goofy-shutdown-secs"></span> ' +
        'second<span class="goofy-shutdown-secs-plural"></span> (' + timesEn +
        ').<br>' +
        'To cancel, press the Escape key.</p>' +
        '<p>将会在<span class="goofy-shutdown-secs"></span>秒内' + verbZh +
        '（' + timesZh + '）.<br>按ESC键取消.</p>');

    var progressBar = new goog.ui.ProgressBar();
    progressBar.render(this.shutdownDialog.getContentElement());

    function tick() {
        var now = new Date().getTime() / 1000.0;

        var startTime = shutdownInfo.time - shutdownInfo.delay_secs;
        var endTime = shutdownInfo.time;
        var fraction = (now - startTime) / (endTime - startTime);
        progressBar.setValue(goog.math.clamp(fraction, 0, 1) * 100);

        var secondsLeft = 1 + Math.floor(Math.max(0, endTime - now));
        goog.array.forEach(
            goog.dom.getElementsByClass('goofy-shutdown-secs'), function(elt) {
                elt.innerHTML = secondsLeft;
            }, this);
        goog.array.forEach(
            goog.dom.getElementsByClass('goofy-shutdown-secs-plural'),
            function(elt) {
                elt.innerHTML = secondsLeft == 1 ? '' : 's';
            }, this);
    }

    var timer = new goog.Timer(20);
    goog.events.listen(timer, goog.Timer.TICK, tick, false, this);
    timer.start();

    goog.events.listen(this.shutdownDialog,
                       goog.ui.PopupBase.EventType.BEFORE_HIDE,
                       function(event) {
                           timer.dispose();
                       }, false, this);

    function onKey(e) {
        if (e.keyCode == goog.events.KeyCodes.ESC) {
            this.sendEvent('goofy:cancel_shutdown', {});
            // Wait for Goofy to reset the pending_shutdown data.
        }
    }
    goog.events.listen(this.shutdownDialog.getElement(),
                       goog.events.EventType.KEYDOWN, onKey, false, this);

    this.shutdownDialog.setButtonSet(null);
    this.shutdownDialog.setHasTitleCloseButton(false);
    this.shutdownDialog.setEscapeToCancel(false);
    goog.dom.classes.add(this.shutdownDialog.getElement(),
                         'goofy-shutdown-dialog');
    this.shutdownDialog.setVisible(true);
    // The dialog has no close box or buttons, so focus is a little weird.
    // If it does lose focus, return it to the dialog.
    goog.events.listen(
        this.shutdownDialog.getElement(), goog.events.EventType.BLUR,
        function(event) {
            goog.Timer.callOnce(goog.bind(this.shutdownDialog.focus,
                                          this.shutdownDialog));
        }, false, this);
};

/**
 * Handles a keyboard shortcut.
 * @param {string} key the key that was depressed (e.g., 'a' for Alt-A).
 */
cros.factory.Goofy.prototype.handleShortcut = function(key) {
    for (var path in this.pathTestMap) {
        var test = this.pathTestMap[path];
        if (test.kbd_shortcut &&
            test.kbd_shortcut.toLowerCase() == key.toLowerCase()) {
            this.sendEvent('goofy:restart_tests', {path: path});
            return;
        }
    }
};

/**
 * Does "auto-run": run all tests that have not yet passed.
 */
cros.factory.Goofy.prototype.startAutoTest = function() {
    this.sendEvent('goofy:run_tests_with_status', {
        'status': ['UNTESTED', 'ACTIVE', 'FAILED']});
}

/**
 * Makes a menu item for a context-sensitive menu.
 *
 * TODO(jsalz): Figure out the correct logic for this and how to localize this.
 * (Please just consider this a rough cut for now!)
 *
 * @param {string} verbEn the action in English.
 * @param {string} verbZh the action in Chinese.
 * @param {string} adjectiveEn a descriptive adjective for the tests (e.g.,
 *     'failed').
 * @param {string} adjectiveZh the adjective in Chinese.
 * @param {number} count the number of tests.
 * @param {cros.factory.TestListEntry} test the name of the root node containing
 *     the tests.
 * @param {Object} handler the handler function (see goog.events.listen).
 * @param {boolean=} opt_adjectiveAtEnd put the adjective at the end in English
 *     (e.g., tests that have *not passed*)
 * @param {string=} opt_suffixEn a suffix in English (e.g.,
 *     ' and continue testing')
 * @param {string=} opt_suffixZh a suffix in Chinese (e.g., '並繼續')
 */
cros.factory.Goofy.prototype.makeMenuItem = function(
    verbEn, verbZh, adjectiveEn, adjectiveZh, count, test, handler,
    opt_adjectiveAtEnd, opt_suffixEn, opt_suffixZh) {

    var labelEn = verbEn + ' ';
    var labelZh = verbZh;
    if (!test.subtests.length) {
        // Leaf node (there will always be both a label_en and label_zh)
        labelEn += (opt_adjectiveAtEnd ? '' : adjectiveEn) +
            ' test “' + test.label_en + '”';
        labelZh += adjectiveZh + '测试' + '「' + test.label_zh + '」';
    } else {
        labelEn += count + ' ' + (opt_adjectiveAtEnd ? '' : adjectiveEn) + ' ' +
            (count == 1 ? 'test' : 'tests');
        if (test.label_en) {
            // Not the root node; include the name
            labelEn += ' in "' + goog.string.htmlEscape(test.label_en) + '"';
        }

        labelZh += count + '个' + adjectiveZh;
        if (test.label_zh) {
            // Not the root node; include the name
            labelZh += '在「' + goog.string.htmlEscape(test.label_zh) + '」里面';
        }
        labelZh += '的测试';
    }

    if (opt_adjectiveAtEnd) {
        labelEn += ' that ' + (count == 1 ? 'has' : 'have') + ' not passed';
    }
    if (opt_suffixEn) {
        labelEn += opt_suffixEn;
    }
    if (opt_suffixZh) {
        labelZh += opt_suffixZh;
    }

    var item = new goog.ui.MenuItem(cros.factory.Content(labelEn, labelZh));
    item.setEnabled(count != 0);
    goog.events.listen(item, goog.ui.Component.EventType.ACTION,
                       handler, true, this);
    return item;
};

/**
 * Returns true if all tests in the test lists before a given test have been
 * run.
 * @param {cros.factory.TestListEntry} test
 */
cros.factory.Goofy.prototype.allTestsRunBefore = function(test) {
    var root = this.pathTestMap[''];

    // Create a stack containing only the root node, and walk through
    // it depth-first.  (Use a stack rather than recursion since we
    // want to be able to bail out easily when we hit 'test' or an
    // incomplete test.)
    var stack = [root];
    while (stack) {
        var item = stack.pop();
        if (item == test) {
            return true;
        }
        if (item.subtests.length) {
            // Append elements in right-to-left order so we will
            // examine them in the correct order.
            var copy = goog.array.clone(item.subtests);
            copy.reverse();
            goog.array.extend(stack, copy);
        } else {
            if (item.state.status == 'ACTIVE' ||
                item.state.status == 'UNTESTED') {
                return false;
            }
        }
    }
    // We should never reach this, since it means that we never saw
    // test while iterating!
    throw Error('Test not in test list');
};

/**
 * Displays a context menu for a test in the test tree.
 * @param {string} path the path of the test whose context menu should be
 *     displayed.
 * @param {Element} labelElement the label element of the node in the test
 *     tree.
 * @param {Array.<goog.ui.Control>=} extraItems items to prepend to the
 *     menu.
 */
cros.factory.Goofy.prototype.showTestPopup = function(path, labelElement,
                                                      extraItems) {
    var test = this.pathTestMap[path];

    if (path == this.lastContextMenuPath &&
        (goog.now() - this.lastContextMenuHideTime <
         goog.ui.PopupBase.DEBOUNCE_DELAY_MS)) {
        // We just hid it; don't reshow.
        return false;
    }

    // If it's a leaf node, and it's the active but not the visible
    // test, ask the backend to make it visible.
    if (test.state.status == 'ACTIVE' &&
        !/** @type boolean */(test.state.visible) &&
        !test.subtests.length) {
        this.sendEvent('goofy:set_visible_test', {'path': path});
    }

    // Hide all tooltips so that they don't fight with the context menu.
    goog.array.forEach(this.tooltips, function(tooltip) {
            tooltip.setVisible(false);
        });

    var menu = this.contextMenu = new goog.ui.PopupMenu();
    function addSeparator() {
        if (menu.getChildCount() &&
            !(menu.getChildAt(menu.getChildCount() - 1)
              instanceof goog.ui.MenuSeparator)) {
            menu.addChild(new goog.ui.MenuSeparator(), true);
        }
    }

    this.lastContextMenuPath = path;

    var numLeaves = 0;
    var numLeavesByStatus = {};
    var allPaths = [];
    var activeAndDisableAbort = false;
    function countLeaves(test) {
        allPaths.push(test.path);
        goog.array.forEach(test.subtests, function(subtest) {
                countLeaves(subtest);
            }, this);

        if (!test.subtests.length) {
            ++numLeaves;
            numLeavesByStatus[test.state.status] = 1 + (
                numLeavesByStatus[test.state.status] || 0);
            // If there is any subtest that is active and can not be aborted,
            // this test can not be aborted.
            if (test.state.status == 'ACTIVE' && test.disable_abort) {
                activeAndDisableAbort = true;
            }
        }
    }
    countLeaves(test);

    if (this.noteDisplay) {
        var item = new goog.ui.MenuItem(cros.factory.Content(
            'Critical factory note; cannot run tests',
            '工厂测试已停止'));
        menu.addChild(item, true);
        item.setEnabled(false);
    } else if (!this.engineeringMode && !this.allTestsRunBefore(test)) {
        var item = new goog.ui.MenuItem(cros.factory.Content(
            'Not in engineering mode; cannot skip tests',
            '工程模式才能跳过测试'));
        menu.addChild(item, true);
        item.setEnabled(false);
    } else {
        var allUntested = numLeavesByStatus['UNTESTED'] == numLeaves;
        var restartOrRunEn = allUntested ? 'Run' : 'Restart';
        var restartOrRunZh = allUntested ? '执行' : '重跑';
        if (numLeaves > 1) {
            restartOrRunEn += ' all';
            restartOrRunZh += '所有的';
        }
        if (this.engineeringMode ||
            (!test.subtests.length && test.state.status != 'PASSED')) {
            // Allow user to restart all tests under a particular node if
            // (a) in engineering mode, or (b) if this is a single non-passed
            // test.  If neither of these is true, it's too easy to
            // accidentally re-run a bunch of tests and wipe their state.
            menu.addChild(this.makeMenuItem(
                restartOrRunEn, restartOrRunZh, '', '', numLeaves, test,
                function(event) {
                    this.sendEvent('goofy:restart_tests', {'path': path});
                }), true);
        }
        if (test.subtests.length) {
            // Only show for parents.
            menu.addChild(this.makeMenuItem(
                'Restart', '重跑', 'not passed', '未成功',
                (numLeavesByStatus['UNTESTED'] || 0) +
                (numLeavesByStatus['ACTIVE'] || 0) +
                (numLeavesByStatus['FAILED'] || 0),
                test, function(event) {
                    this.sendEvent('goofy:run_tests_with_status', {
                        'status': ['UNTESTED', 'ACTIVE', 'FAILED'],
                        'path': path
                    });
                }, /*opt_adjectiveAtEnd=*/true), true);
        }
        if (this.engineeringMode) {
            menu.addChild(this.makeMenuItem(
                'Clear status of', '清除', '', '', numLeaves, test,
                function(event) {
                    this.sendEvent('goofy:clear_state', {'path': path});
                    }, false, '', '的狀態'), true);
        }
        if (this.engineeringMode && test.subtests.length) {
            menu.addChild(this.makeMenuItem(
                'Run', '执行', 'untested', '未测的',
                (numLeavesByStatus['UNTESTED'] || 0) +
                    (numLeavesByStatus['ACTIVE'] || 0),
                test, function(event) {
                    this.sendEvent('goofy:auto_run', {'path': path});
                }), true);
        }
    }
    addSeparator();

    var stopAllItem = new goog.ui.MenuItem(cros.factory.Content(
        'Stop all tests',
        '停止所有的测试'));
    stopAllItem.setEnabled(numLeavesByStatus['ACTIVE'] > 0);
    menu.addChild(stopAllItem, true);
    goog.events.listen(
        stopAllItem, goog.ui.Component.EventType.ACTION,
        function(event) {
            this.sendEvent('goofy:stop', {
                'fail': true, 'reason': 'Operator requested abort'});
        }, true, this);

    // When there is any active test, enable abort item in menu
    // if goofy is in engineering mode or there is no
    // active subtest with disable_abort=true.
    if (numLeavesByStatus['ACTIVE'] &&
        (this.engineeringMode || !activeAndDisableAbort)) {
      menu.addChild(this.makeMenuItem(
          'Abort', '取消', 'active', '執行中的',
          numLeavesByStatus['ACTIVE'] || 0,
          test, function(event) {
              this.sendEvent('goofy:stop', {
                  'path': path, 'fail': true,
                  'reason': 'Operator requested abort'});
          }, false, ' and continue testing', '並繼續'), true);
    }

    if (this.engineeringMode && !test.subtests.length) {
        addSeparator();
        menu.addChild(this.createViewLogMenu(path), true);
    }

    if (extraItems && extraItems.length) {
        addSeparator();
        goog.array.forEach(extraItems, function(item) {
                menu.addChild(item, true);
            }, this);
    }

    menu.render(document.body);
    menu.showAtElement(labelElement,
                     goog.positioning.Corner.BOTTOM_LEFT,
                     goog.positioning.Corner.TOP_LEFT);
    goog.events.listen(menu, goog.ui.Component.EventType.HIDE,
                       function(event) {
                           if (event.target != menu) {
                               // We also receive HIDE events for
                               // submenus, but we're interested only
                               // in events for this top-level menu.
                               return;
                           }
                           menu.dispose();
                           this.contextMenu = null;
                           this.lastContextMenuHideTime = goog.now();
                           // Return focus to visible test, if any.
                           this.focusInvocation();
                       }, true, this);
    return true;
};

cros.factory.Goofy.prototype.HMS_TIME_FORMAT =
    new goog.i18n.DateTimeFormat('HH:mm:ss');
/**
 * Returns a "View logs" submenu for a given test path.
 * @param path string
 * @return goog.ui.SubMenu
 */
cros.factory.Goofy.prototype.createViewLogMenu = function(path) {
    var subMenu = new goog.ui.SubMenu('View logs');
    var loadingItem = new goog.ui.MenuItem('Loading...');
    loadingItem.setEnabled(false);
    subMenu.addItem(loadingItem);

    this.sendRpc('get_test_history', [path], function(history) {
            if (subMenu.getMenu().indexOfChild(loadingItem) >= 0) {
                subMenu.getMenu().removeChild(loadingItem, true);
            }

            if (!history.length) {
                loadingItem.setCaption('No logs available');
                return;
            }

            // Arrange in descending order of time (it is returned in
            // ascending order).
            history.reverse();

            var count = history.length;
            goog.array.forEach(history, function(untypedEntry) {
                var entry = /** @type cros.factory.HistoryMetadata */(
                    untypedEntry);
                var status = entry.status ? entry.status.toLowerCase() :
                    'started';
                var title = count-- + '. Run at ';

                if (entry.init_time) {
                    // TODO(jsalz): Localize (but not that important since this
                    // is not for operators)

                    title += this.HMS_TIME_FORMAT.format(
                        new Date(entry.init_time * 1000));
                }
                title += ' (' + status;

                var time = entry.end_time || entry.init_time;
                if (time) {
                    var secondsAgo = goog.now() / 1000.0 - time;

                    var hoursAgo = Math.floor(secondsAgo / 3600);
                    secondsAgo -= hoursAgo * 3600;

                    var minutesAgo = Math.floor(secondsAgo / 60);
                    secondsAgo -= minutesAgo * 60;

                    title += ' ';
                    if (hoursAgo) {
                        title += hoursAgo + ' h ';
                    }
                    if (minutesAgo) {
                        title += minutesAgo + ' m ';
                    }
                    title += Math.floor(secondsAgo) + ' s ago';
                }
                title += ')…';

                var item = new goog.ui.MenuItem(
                    goog.dom.createDom('span',
                                       'goofy-view-logs-status-' + status,
                                       title));
                goog.events.listen(
                    item, goog.ui.Component.EventType.ACTION,
                    function(event) {
                        this.showHistoryEntry(entry.path, entry.invocation);
                    }, false, this);

                subMenu.addItem(item);
            }, this);
        });

    return subMenu;
};

/**
 * Displays a dialog containing logs.
 * @param {string} titleHTML
 * @param {string} data text to show in the dialog.
 */
cros.factory.Goofy.prototype.showLogDialog = function(titleHTML, data) {
    var dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    dialog.setModal(false);

    var viewSize = goog.dom.getViewportSize(
        goog.dom.getWindow(document) || window);
    var maxWidth = viewSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
    var maxHeight = viewSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;

    dialog.setContent('<div class="goofy-log-data"' +
                      ' style="max-width: ' + maxWidth +
                      '; max-height: ' + maxHeight + '">' +
                      goog.string.htmlEscape(data) +
                      '</div>' +
                      '<div class="goofy-log-time"></div>');
    dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
    dialog.setVisible(true);
    cros.factory.Goofy.setDialogTitleHTML(dialog, titleHTML);

    var logDataElement = goog.dom.getElementByClass('goofy-log-data',
                                                    dialog.getContentElement());
    logDataElement.scrollTop = logDataElement.scrollHeight;

    var logTimeElement = goog.dom.getElementByClass('goofy-log-time',
                                                    dialog.getContentElement());
    var timer = new goog.Timer(1000);
    goog.events.listen(timer, goog.Timer.TICK, function(event) {
            // Show time in the same format as in the logs
            logTimeElement.innerHTML = (
                cros.factory.Label('System time: ',
                                   '系统时间：') +
                new goog.date.DateTime().toUTCIsoString(true, true).
                    replace(' ', 'T'));
        }, false, this);
    timer.dispatchTick();
    timer.start();
    goog.events.listen(dialog, goog.ui.Component.EventType.HIDE,
                       function(event) {
                           timer.dispose();
                       }, false, this);
};


/**
 * Displays a dialog containing the contents of /var/log/messages.
 */
cros.factory.Goofy.prototype.viewVarLogMessages = function() {
    this.sendRpc(
        'GetVarLogMessages', [],
        function(data) {
            this.showLogDialog('/var/log/messages', data);
        });
};

/**
 * Displays a dialog containing the contents of /var/log/messages
 * before the last reboot.
 */
cros.factory.Goofy.prototype.viewVarLogMessagesBeforeReboot = function() {
    this.sendRpc(
        'GetVarLogMessagesBeforeReboot', [],
        function(data) {
            data = data || 'Unable to find log message indicating reboot.';
            this.showLogDialog(
                cros.factory.Label('/var/log/messages before last reboot',
                                   '上次重开机前的 /var/log/messages'),
                data);
        });
};

/**
 * Displays a dialog containing the contents of dmesg.
 */
cros.factory.Goofy.prototype.viewDmesg = function() {
    this.sendRpc(
        'GetDmesg', [],
        function(data) {
            this.showLogDialog('dmesg', data);
        });
};

/**
 * Add a factory note.
 * @param {string} name
 * @param {string} note
 */
cros.factory.Goofy.prototype.addNote = function(name, note, level) {
    if (!name || !note) {
        alert('Both fields must not be empty!');
        return false;
    }
    this.sendRpc('AddNote',
                 [new cros.factory.Note(
                      name,
                      note,
                      new goog.date.DateTime().toUTCIsoString(true, true),
                      level)],
                 this.updateNote);
    return true;
};

/**
 * Displays a dialog to modify factory note.
 */
cros.factory.Goofy.prototype.showNoteDialog = function() {
    var dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    dialog.setModal(true);
    this.noteDialog = dialog;

    var viewSize = goog.dom.getViewportSize(
        goog.dom.getWindow(document) || window);
    var maxWidth = viewSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
    var maxHeight = viewSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;

    var noteTable = [];
    noteTable.push('<table class="goofy-addnote-table">');
    noteTable.push(
        '<tr><th>' +
        cros.factory.Content('Your Name', '你的名字').innerHTML +
        '</th><td>' +
        '<input id="goofy-addnote-name" style="max-width: ' +
        maxWidth + '"></td></tr>');
    noteTable.push(
        '<tr><th>' +
        cros.factory.Content('Note Content', '注记内容').innerHTML +
        '</th><td>' +
        '<textarea id="goofy-addnote-text" style="max-width: ' +
        maxWidth + '; max-height: ' + maxHeight + '">' +
        '</textarea></td></tr>');
    noteTable.push(
        '<tr><th>' +
        cros.factory.Content('Severity', '严重性').innerHTML +
        '</th><td>' +
        '<select id="goofy-addnote-level">');
    goog.array.forEach(cros.factory.NOTE_LEVEL, function(lvl) {
        noteTable.push('<option value="' + lvl['name'] + '"');
        if (lvl['name'] == 'INFO')
            noteTable.push(' default');
        noteTable.push('>' + lvl['name'] + ': ' + lvl['message'] + '</option>');
    }, this);
    noteTable.push('</td></tr>');
    noteTable.push('</table>');

    dialog.setContent(noteTable.join(''));
    var buttons = goog.ui.Dialog.ButtonSet.createOkCancel();
    dialog.setButtonSet(buttons);
    dialog.setVisible(true);
    cros.factory.Goofy.setDialogTitleHTML(
            dialog,
            cros.factory.Content('Add Note', '新增注记').innerHTML);

    var nameBox = document.getElementById('goofy-addnote-name');
    var textBox = document.getElementById('goofy-addnote-text');
    var levelBox = document.getElementById('goofy-addnote-level');

    goog.events.listen(dialog, goog.ui.Dialog.EventType.SELECT,
                       function(event) {
                           if (event.key == "ok") {
                               return this.addNote(
                                   nameBox.value,
                                   textBox.value,
                                   levelBox.value);
                           }
                       }, false, this);
};

/**
 * Uploads factory logs to the shop floor server.
 * @param {string} name name of the person uploading logs
 * @param {string} serial serial number of this device
 * @param {string} description bug description
 * @param {function()} onSuccess function to execute on success
 */
cros.factory.Goofy.prototype.uploadFactoryLogs = function(
    name, serial, description, onSuccess) {
    var dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    var content = cros.factory.Content(
        'Uploading factory logs...',
        '正在上载工厂记录...');
    dialog.setTitle(content);
    dialog.setContent(
        cros.factory.Label(
            'Uploading factory logs.  Please wait...',
            '正在上载工厂记录 。 请 稍等...') + '<br>');

    dialog.setButtonSet(null);
    dialog.setVisible(true);

    this.sendRpc('UploadFactoryLogs', [name, serial, description],
                 function(info) {
                     var filename = /** @type string */(info[0]);
                     var size = /** @type number */(info[1]);
                     var key = /** @type string */(info[2]);

                     dialog.setContent(
                         'Success! Uploaded factory logs (' +
                             size + ' bytes).<br><br>' +
                             'The archive key is ' +
                             '<span class="goofy-ul-archive-key">' +
                             goog.string.htmlEscape(key) + '</span>.<br>' +
                             'Please use this key when filing bugs<br>' +
                             'or corresponding with the factory team.');
                     dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
                     dialog.reposition();

                     onSuccess();
                 },
                 function(response) {
                     dialog.setContent(
                         'Unable to upload factory logs:<br>' +
                             goog.string.htmlEscape(response.error.message));
                     dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
                     dialog.reposition();
                 });
};

/**
 * Pings the shopfloor server, displayed an alert if it cannot be reached.
 * @param {function()} onSuccess function to execute on success
 */
cros.factory.Goofy.prototype.pingShopFloorServer = function(onSuccess) {
    this.sendRpc('PingShopFloorServer', [], onSuccess,
                 function(response) {
                     this.alert('Unable to contact shopfloor server.<br>' +
                                goog.string.htmlEscape(response.error.message));
                 });
};

/**
 * Displays a dialog to upload factory logs to shopfloor server.
 */
cros.factory.Goofy.prototype.showUploadFactoryLogsDialog = function() {
    var dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    dialog.setModal(true);

    var table = [];
    table.push('<table class="goofy-ul-table">');
    table.push(
        '<tr><th>' +
        cros.factory.Content('Your Name', '你的名字').innerHTML +
        '</th><td>' +
        '<input id="goofy-ul-name" size="30">' +
        '</td></tr>');
    table.push(
        '<tr><th>' +
        cros.factory.Content('Serial Number', '编号').innerHTML +
        '</th><td>' +
        '<input id="goofy-ul-serial" size="30" value="' +
        goog.string.htmlEscape(
            /** @type string */(this.systemInfo['serial_number']) ||
            /** @type string */(this.systemInfo['mlb_serial_number']) ||
                '') +
        '"></td></tr>');
    table.push(
        '<tr><th>' +
        cros.factory.Content('Bug Description', 'Bug 描述').innerHTML +
        '</th><td>' +
        '<input id="goofy-ul-description" size="50">' +
        '</td></tr>');
    table.push('</table>');

    dialog.setContent(table.join(''));
    var buttons = goog.ui.Dialog.ButtonSet.createOkCancel();
    dialog.setButtonSet(buttons);
    dialog.setTitle(
        cros.factory.Content('Upload Factory Logs', '上载工厂记录'));
    dialog.setVisible(true);

    var nameElt = document.getElementById('goofy-ul-name');
    var serialElt = document.getElementById('goofy-ul-serial');
    var descriptionElt = document.getElementById('goofy-ul-description');

    // Enable OK only if all three of these text fields are filled in.
    var elts = [nameElt, serialElt, descriptionElt];
    function checkOKEnablement() {
        buttons.setButtonEnabled(goog.ui.Dialog.DefaultButtonKeys.OK, true);
        goog.array.forEach(elts, function(elt) {
            if (goog.string.isEmpty(elt.value)) {
                buttons.setButtonEnabled(goog.ui.Dialog.DefaultButtonKeys.OK,
                                         false);
            }
        }, this);
    }
    goog.array.forEach(elts, function(elt) {
        goog.events.listen(elt, [goog.events.EventType.CHANGE,
                                 goog.events.EventType.KEYUP],
                           checkOKEnablement, false, this);
    });
    checkOKEnablement();

    goog.events.listen(
        dialog, goog.ui.Dialog.EventType.SELECT,
        function(event) {
            if (event.key != goog.ui.Dialog.DefaultButtonKeys.OK)
                return;

            this.uploadFactoryLogs(
                nameElt.value, serialElt.value, descriptionElt.value,
                function() { dialog.dispose() });

            event.preventDefault();
        }, false, this);
};

/**
 * Saves factory logs to a USB drive.
 */
cros.factory.Goofy.prototype.saveFactoryLogsToUSB = function() {
    var titleContent = cros.factory.Content(
        'Save Factory Logs to USB', '保存工厂记录到 U盘');

    function doSave() {
        function callback(id) {
            if (id == null) {
                // Cancelled.
                return;
            }

            var dialog = new goog.ui.Dialog();
            this.registerDialog(dialog);
            dialog.setTitle(titleContent);
            dialog.setContent(
                cros.factory.Label('Saving factory logs to USB drive...',
                                   '正在保存工厂记录到 U盘...'));
            dialog.setButtonSet(null);
            dialog.setVisible(true);
            this.positionOverConsole(dialog.getElement());
            this.sendRpc('SaveLogsToUSB', [id],
                function(info) {
                    var dev = info[0];
                    var filename = info[1];
                    var size = info[2];
                    var temporary = info[3];

                    dialog.setContent(
                        cros.factory.Label(
                            'Success! Saved factory logs (' + size +
                            ' bytes) to ' + dev + ' as<br>' + filename + '.' +
                            (temporary ? ' The drive has been unmounted.' : ''),
                            '保存工厂记录 (' + size +
                            ' bytes) 到 U盘 ' +
                            dev + ' 已成功，文件叫<br>' +
                            filename + '。' +
                            (temporary ? 'U盘已卸载。' : '')));
                    dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
                    this.positionOverConsole(dialog.getElement());
                }, function(response) {
                    dialog.setContent(
                        'Unable to save logs: ' +
                        goog.string.htmlEscape(response.error.message));
                    dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
                    this.positionOverConsole(dialog.getElement());
                });
        }

        var idDialog = new goog.ui.Prompt(
            titleContent,
            cros.factory.Label(
                'Enter an optional identifier for the archive ' +
                '(or press Enter for none):',
                '请输入识別号给工厂记录文件，' +
                '或按回车键不选：'),
            goog.bind(callback, this));
        this.registerDialog(idDialog);
        idDialog.setVisible(true);
        goog.dom.classes.add(idDialog.getElement(),
                             'goofy-log-identifier-prompt');
        this.positionOverConsole(idDialog.getElement());
    }

    // Active timer, if any.
    var timer = null;

    var waitForUSBDialog = new goog.ui.Dialog();
    this.registerDialog(waitForUSBDialog);
    waitForUSBDialog.setContent(
        cros.factory.Label('Please insert a formatted USB stick<br>' +
                           'and wait a moment for it to be mounted.',
                           '请插入 U盘后稍等掛载。'));
    waitForUSBDialog.setButtonSet(
        new goog.ui.Dialog.ButtonSet().
            addButton(goog.ui.Dialog.ButtonSet.DefaultButtons.CANCEL,
                      false, true));
    waitForUSBDialog.setTitle(titleContent);

    function waitForUSB() {
        function restartWaitForUSB() {
            waitForUSBDialog.setVisible(true);
            this.positionOverConsole(waitForUSBDialog.getElement());
            timer = goog.Timer.callOnce(goog.bind(waitForUSB, this),
                                        cros.factory.MOUNT_USB_DELAY_MSEC);
        }
        this.sendRpc(
            'IsUSBDriveAvailable', [],
            function(available) {
                if (available) {
                    waitForUSBDialog.dispose();
                    doSave.call(this);
                } else {
                    restartWaitForUSB.call(this);
                }
            }, goog.bind(restartWaitForUSB, this));
    }
    goog.events.listen(waitForUSBDialog, goog.ui.Component.EventType.HIDE,
                       function(event) {
                           if (timer) {
                               goog.Timer.clear(timer);
                           }
                       }, false, this);
    waitForUSB.call(this);
};

cros.factory.Goofy.prototype.FULL_TIME_FORMAT =
    new goog.i18n.DateTimeFormat('yyyy-MM-dd HH:mm:ss.SSS');
/**
 * Displays a dialog containing history for a given test invocation.
 * @param {string} path
 * @param {string} invocation
 */
cros.factory.Goofy.prototype.showHistoryEntry = function(path, invocation) {
    this.sendRpc(
        'get_test_history_entry', [path, invocation],
        function(untypedEntry) {
            var entry = /** @type cros.factory.HistoryEntry */(untypedEntry);

            var viewSize = goog.dom.getViewportSize(
                goog.dom.getWindow(document) || window);
            var maxWidth = viewSize.width *
                cros.factory.MAX_DIALOG_SIZE_FRACTION;
            var maxHeight = viewSize.height *
                cros.factory.MAX_DIALOG_SIZE_FRACTION;

            var metadataTable = [];
            metadataTable.push('<table class="goofy-history-metadata>"');
            goog.array.forEach(
                [['status', 'Status'],
                 ['init_time', 'Creation time'],
                 ['start_time', 'Start time'],
                 ['end_time', 'End time']],
                function(f) {
                    var name = f[0];
                    var title = f[1];

                    if (entry.metadata[name]) {
                        var value = entry.metadata[name];
                        delete entry.metadata[name];
                        if (goog.string.endsWith(name, '_time')) {
                            value = this.FULL_TIME_FORMAT.format(
                                new Date(value * 1000));
                        }
                        metadataTable.push(
                            '<tr><th>' + title + '</th><td>' +
                            goog.string.htmlEscape(value) +
                            '</td></tr>');
                    }
                }, this);

            var keys = goog.object.getKeys(entry.metadata);
            keys.sort();
            goog.array.forEach(keys, function(key) {
                if (key == 'log_tail') {
                    // Skip log_tail, since we already have the
                    // entire log.
                    return;
                }
                metadataTable.push('<tr><th>' + key + '</th><td>' +
                                   goog.string.htmlEscape(entry.metadata[key]) +
                                   '</td></tr>');
                }, this);

            metadataTable.push('</table>');

            var dialog = new goog.ui.Dialog();
            this.registerDialog(dialog);
            dialog.setTitle(entry.metadata.path +
                            ' (invocation ' + entry.metadata.invocation + ')');
            dialog.setModal(false);
            dialog.setContent(
                '<div class="goofy-history" style="max-width: ' +
                maxWidth + '; max-height: ' + maxHeight + '">' +
                '<div class=goofy-history-header>Test Info</div>' +
                metadataTable.join('') +
                '<div class=goofy-history-header>Log</div>' +
                '<div class=goofy-history-log>' +
                goog.string.htmlEscape(entry.log) +
                '</div>' +
                '</div>');
            dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
            dialog.setVisible(true);
        });
};

/**
 * Updates the tooltip for a test based on its status.
 * The tooltip will be displayed only for failed tests.
 * @param {string} path
 * @param {goog.ui.AdvancedTooltip} tooltip
 * @param {goog.events.Event} event the BEFORE_SHOW event that will cause the
 *     tooltip to be displayed.
 */
cros.factory.Goofy.prototype.updateTestToolTip =
    function(path, tooltip, event) {
    var test = this.pathTestMap[path];

    tooltip.setHtml('');

    var errorMsg = test.state['error_msg'];
    if (test.state.status != 'FAILED' || this.contextMenu || !errorMsg) {
        // Just show the test path, with a very short hover delay.
        tooltip.setHtml(test.path);
        tooltip.setHideDelayMs(cros.factory.NON_FAILING_TEST_HOVER_DELAY_MSEC);
    } else {
        // Show the last failure.
        var lines = errorMsg.split('\n');
        var html = (test.path + ' failed:' +
                    '<div class="goofy-test-failure">' +
                    goog.string.htmlEscape(lines.shift()) + '</span>');

        if (lines.length) {
            html += ('<div class="goofy-test-failure-detail-link">' +
                     'Show more detail...</div>' +
                     '<div class="goofy-test-failure-detail">' +
                     goog.string.htmlEscape(lines.join('\n')) + '</div>');
        }
        if (test.state.invocation) {
            html += ('<div class="goofy-test-failure-view-log-link">' +
                     'View log...</div>')
        }

        tooltip.setHtml(html);

        if (lines.length) {
            var link = goog.dom.getElementByClass(
            'goofy-test-failure-detail-link', tooltip.getElement());
            goog.events.listen(
                link, goog.events.EventType.CLICK,
                function(event) {
                    goog.dom.classes.add(tooltip.getElement(),
                                         'goofy-test-failure-expanded');
                    tooltip.reposition();
            }, true, this);
        }
        if (test.state.invocation) {
            var link = goog.dom.getElementByClass(
                'goofy-test-failure-view-log-link', tooltip.getElement());
            goog.events.listen(
                link, goog.events.EventType.CLICK,
                function(event) {
                    tooltip.dispose();
                    this.showHistoryEntry(test.path, test.state.invocation);
                }, false, this);
        }
    }
};

/**
 * Sets up the UI for a the test list.  (Should be invoked only once, when
 * the test list is received.)
 * @param {cros.factory.TestListEntry} testList the test list (the return value
 *     of the get_test_list RPC call).
 */
cros.factory.Goofy.prototype.setTestList = function(testList) {
    cros.factory.logger.info('Received test list: ' +
        goog.debug.expose(testList));
    goog.style.showElement(document.getElementById('goofy-loading'), false);

    this.addToNode(null, testList);
    // expandAll is necessary to get all the elements to actually be
    // created right away so we can add listeners.  We'll collapse it later.
    this.testTree.expandAll();
    this.testTree.render(document.getElementById('goofy-test-tree'));

    var addListener = goog.bind(function(path, labelElement, rowElement) {
        var tooltip = new goog.ui.AdvancedTooltip(rowElement);
        tooltip.setHideDelayMs(1000);
        this.tooltips.push(tooltip);
        goog.events.listen(
            tooltip, goog.ui.Component.EventType.BEFORE_SHOW,
            function(event) {
                this.updateTestToolTip(path, tooltip, event);
            }, true, this);
        goog.events.listen(
            rowElement, goog.events.EventType.CONTEXTMENU,
            function(event) {
                if (event.ctrlKey) {
                    // Ignore; let the default (browser) context menu
                    // show up.
                    return;
                }

                this.showTestPopup(path, labelElement);
                event.stopPropagation();
                event.preventDefault();
            }, true, this);
        goog.events.listen(
            labelElement, goog.events.EventType.MOUSEDOWN,
            function(event) {
                if (event.button == 0) {
                    this.showTestPopup(path, labelElement);
                    event.stopPropagation();
                    event.preventDefault();
                }
            }, true, this);
    }, this);

    for (var path in this.pathNodeMap) {
        var node = this.pathNodeMap[path];
        addListener(path, node.getLabelElement(), node.getRowElement());
    }

    goog.array.forEach([goog.events.EventType.MOUSEDOWN,
                        goog.events.EventType.CONTEXTMENU],
        function(eventType) {
            goog.events.listen(
                document.getElementById('goofy-title'),
                eventType,
                function(event) {
                    if (eventType == goog.events.EventType.MOUSEDOWN &&
                        event.button != 0) {
                        // Only process primary button for MOUSEDOWN.
                        return;
                    }
                    if (event.ctrlKey) {
                        // Ignore; let the default (browser) context menu
                        // show up.
                        return;
                    }

                    var extraItems = [];
                    var addExtraItem = goog.bind(
                        function(labelEn, labelZh, action) {
                            var item = new goog.ui.MenuItem(
                                cros.factory.Content(labelEn, labelZh));
                            goog.events.listen(
                                item,
                                goog.ui.Component.EventType.ACTION,
                                action, false, this);
                            extraItems.push(item);
                        }, this);

                    if (this.engineeringMode) {
                        addExtraItem('Update factory software',
                                     '更新工厂软体',
                                     this.updateFactory);
                        extraItems.push(this.makeSwitchTestListMenu());
                        extraItems.push(new goog.ui.MenuSeparator());
                        addExtraItem('Save note on device', '注记',
                                     this.showNoteDialog);
                        addExtraItem('View notes', '检视注记',
                                     this.viewNotes);
                        extraItems.push(new goog.ui.MenuSeparator());
                        addExtraItem('View /var/log/messages',
                                     '检视 /var/log/messages',
                                     this.viewVarLogMessages);
                        addExtraItem('View /var/log/messages ' +
                                    'before last reboot',
                                    '检视上次重开机前的 ' +
                                     '/var/log/messages',
                                     this.viewVarLogMessagesBeforeReboot);
                        addExtraItem('View dmesg', '检视 dmesg',
                                     this.viewDmesg);
                    }

                    addExtraItem('Save factory logs to USB drive...',
                                 '保存工厂记录到 U盘',
                                 this.saveFactoryLogsToUSB);
                    addExtraItem('Upload factory logs...',
                                 '上载工厂记录',
                                 function() {
                                     this.pingShopFloorServer(
                                         this.showUploadFactoryLogsDialog);
                                 });

                    this.showTestPopup(
                        '', document.getElementById('goofy-logo-text'),
                        extraItems);

                    event.stopPropagation();
                    event.preventDefault();
                }, true, this);
        }, this);

    this.testTree.collapseAll();
    this.sendRpc('get_test_states', [], function(stateMap) {
        for (var path in stateMap) {
            if (!goog.string.startsWith(path, "_")) {  // e.g., __jsonclass__
                this.setTestState(path, stateMap[path]);
            }
        }
    });
};

/**
 * Create the switch test list menu.
 */
cros.factory.Goofy.prototype.makeSwitchTestListMenu = function(menu) {
    var subMenu = new goog.ui.SubMenu(cros.factory.Content(
        'Switch test list', '切换测试列表'));
    goog.object.forEach(this.testLists, function(testList) {
        var item = new goog.ui.MenuItem(testList.name);
        item.setSelectable(true);
        item.setSelected(testList.enabled);
        subMenu.addItem(item);
        if (testList.enabled) {
            // Don't do anything if the active one is selected.
            return;
        }
        goog.events.listen(
            item,
            goog.ui.Component.EventType.ACTION,
            function() {
                var dialog = new goog.ui.Dialog();
                this.registerDialog(dialog);
                dialog.setContent(
                    cros.factory.Label(
                        ('Warning: Switching to test list “' +
                         goog.string.htmlEscape(testList.name) +
                         '” will clear all test state.<br>' +
                         'Are you sure you want to proceed?'),
                        ('警示：切換至测试列表「' +
                         goog.string.htmlEscape(testList.name) +
                         '」将清除所有测试状态。<br>' +
                         '确定要继续吗？')
                        ));

                var buttonSet = new goog.ui.Dialog.ButtonSet();
                buttonSet.addButton(
                    {key: goog.ui.Dialog.DefaultButtonKeys.OK,
                     caption: cros.factory.Content(
                         'Yes, clear state and restart',
                         '确定，清除测试状态並重啓')});
                buttonSet.addButton(
                    {key: goog.ui.Dialog.DefaultButtonKeys.CANCEL,
                     caption: cros.factory.Content('Cancel', '取消')},
                    true, true);
                dialog.setButtonSet(buttonSet);
                dialog.setVisible(true);

                var titleEn = 'Switch Test List: ' +
                    goog.string.htmlEscape(testList.name);
                var titleZh = '切换测试列表：' + goog.string.htmlEscape(testList.name);

                cros.factory.Goofy.setDialogTitleHTML(
                    dialog,
                    cros.factory.Label(titleEn, titleZh));
                dialog.reposition();

                goog.events.listen(
                    dialog, goog.ui.Dialog.EventType.SELECT, function(e) {
                        if (e.key == goog.ui.Dialog.DefaultButtonKeys.OK) {
                            var dialog = this.showIndefiniteActionDialog(
                                titleEn,
                                'Switching test list.  Please wait...',
                                titleZh,
                                '正在切换测试列表，请稍等...');
                            this.sendRpc(
                                'SwitchTestList', [testList.id],
                                null,  // No action on success; wait to die.
                                function(response) {
                                    dialog.dispose();
                                    this.alert(
                                        'Unable to switch test list:<br>' +
                                        goog.string.htmlEscape(
                                            response.error.message));
                                });
                        }
                    }, false, this);
            }, false, this);
    }, this);
    return subMenu;
};

/**
 * Displays a dialog for an operation that should never return.
 * @param {string} titleEn
 * @param {string} labelEn
 * @param {string=} titleZh
 * @param {string=} labelZh
 * @return {goog.ui.Dialog}
 */
cros.factory.Goofy.prototype.showIndefiniteActionDialog = function(
    titleEn, labelEn, titleZh, labelZh) {
    var dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    dialog.setHasTitleCloseButton(false);
    dialog.setContent(cros.factory.Label(labelEn, labelZh));
    dialog.setButtonSet(null);
    dialog.setVisible(true);
    cros.factory.Goofy.setDialogTitleHTML(
        dialog, cros.factory.Label(titleEn, titleZh));
    dialog.reposition();
    return dialog;
};

/**
 * Sends an event to update factory software.
 * @export
 */
cros.factory.Goofy.prototype.updateFactory = function() {
    var dialog = this.showIndefiniteActionDialog(
        'Software update',
        'Updating factory software. Please wait...',
        '更新工厂软体',
        '正在更新工厂软体，请稍等...');

    this.sendRpc(
        'UpdateFactory', [], function(ret) {
            var success = ret[0];
            var updated = ret[1];
            var restartTime = ret[2];
            var errorMsg = ret[3];

            if (updated) {
                dialog.setTitle('Update succeeded');
                dialog.setContent(
                    cros.factory.Label(
                        'Update succeeded. Restarting.',
                        '更新已成功，' +
                        '将会在几秒钟之内重新启动。'));
            } else if (success) {  // but not updated
                dialog.setContent(cros.factory.Label(
                    'No update is currently necessary.',
                    '目前不用更新工厂软体'));
                dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
            } else {
                dialog.setContent(
                    cros.factory.Label('Update failed:',
                                       '更新失败了：') +
                    '<pre>' + goog.string.htmlEscape(errorMsg) + '</pre>');
                dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
            }
            dialog.reposition();
        });
};

/**
 * Sets the state for a particular test.
 * @param {string} path
 * @param {cros.factory.TestState} state the TestState object (contained in
 *     an event or as a response to the RPC call).
 */
cros.factory.Goofy.prototype.setTestState = function(path, state) {
    var node = this.pathNodeMap[path];
    if (!node) {
        cros.factory.logger.warning('No node found for test path ' + path);
        return;
    }

    var elt = this.pathNodeMap[path].getElement();
    var test = this.pathTestMap[path];
    test.state = state;

    // Assign the appropriate class to the node, and remove all other
    // status classes.
    goog.dom.classes.addRemove(
        elt,
        goog.array.filter(
            goog.dom.classes.get(elt),
            function(cls) {
                return goog.string.startsWith(cls, "goofy-status-") && cls
            }),
        'goofy-status-' + state.status.toLowerCase());

    goog.dom.classes.enable(elt, 'goofy-skip', state.skip);

    var visible = state.visible;
    goog.dom.classes.enable(elt, 'goofy-test-visible', visible);
    goog.object.forEach(this.invocations, function(invoc, uuid) {
            if (invoc && invoc.path == path) {
                goog.dom.classes.enable(invoc.iframe,
                                        'goofy-test-visible', visible);
                if (visible) {
                    invoc.iframe.contentWindow.focus();
                }
            }
        }, this);

    if (state.status == 'ACTIVE') {
        // Automatically show the test if it is running.
        node.reveal();
    } else if (cros.factory.AUTO_COLLAPSE) {
        // If collapsible, then collapse it in 250ms if still inactive.
        if (node.getChildCount() != 0) {
            window.setTimeout(function(event) {
                    if (test.state.status != 'ACTIVE') {
                        node.collapse();
                    }
                }, 250);
        }
    }
};

/**
 * Adds a test node to the tree.
 *
 * Also normalizes the test node by adding label_zh if not present.  (The root
 * node will have neither label.)
 *
 * @param {goog.ui.tree.BaseNode} parent
 * @param {cros.factory.TestListEntry} test
 */
cros.factory.Goofy.prototype.addToNode = function(parent, test) {
    var node;
    if (parent == null) {
        node = this.testTree;
    } else {
        test.label_zh = test.label_zh || test.label_en;

        var label = '<span class="goofy-label-en">' +
            goog.string.htmlEscape(test.label_en) + '</span>';
        label += '<span class="goofy-label-zh">' +
            goog.string.htmlEscape(test.label_zh) + '</span>';
        if (test.kbd_shortcut) {
            label = '<span class="goofy-kbd-shortcut">Alt-' +
                goog.string.htmlEscape(test.kbd_shortcut.toUpperCase()) +
                '</span>' + label;
        }
        node = this.testTree.createNode(label);
        parent.addChild(node);
    }
    goog.array.forEach(test.subtests, function(subtest) {
            this.addToNode(node, subtest);
        }, this);

    node.setIconClass('goofy-test-icon');
    node.setExpandedIconClass('goofy-test-icon');

    this.pathNodeMap[test.path] = node;
    this.pathTestMap[test.path] = test;
    this.pathNodeIdMap[test.path] = node.getId();
    node.factoryTest = test;
};

/**
 * Sends an event to Goofy.
 * @param {string} type the event type (e.g., 'goofy:hello').
 * @param {Object} properties of event.
 */
cros.factory.Goofy.prototype.sendEvent = function(type, properties) {
    var dict = goog.object.clone(properties);
    dict.type = type;
    var serialized = goog.json.serialize(dict);
    cros.factory.logger.info('Sending event: ' + serialized);
    this.ws.send(serialized);
};

/**
 * Calls an RPC function and invokes callback with the result.
 * @param {Object} args
 * @param {Object=} callback
 * @param {Object=} opt_errorCallback
 */
cros.factory.Goofy.prototype.sendRpc = function(
    method, args, callback, opt_errorCallback) {
    var request = goog.json.serialize({method: method, params: args, id: 1});
    cros.factory.logger.info('RPC request: ' + request);
    var factoryThis = this;
    goog.net.XhrIo.send(
        '/', function() {
            cros.factory.logger.info('RPC response for ' + method + ': ' +
                                     this.getResponseText());

            if (this.getLastErrorCode() != goog.net.ErrorCode.NO_ERROR) {
                factoryThis.logToConsole('RPC error calling ' + method + ': ' +
                    goog.net.ErrorCode.getDebugMessage(this.getLastErrorCode()),
                    'goofy-internal-error');
                // TODO(jsalz): handle error
                return;
            }

            var response = goog.json.unsafeParse(this.getResponseText());
            if (response.error) {
                if (opt_errorCallback) {
                    opt_errorCallback.call(factoryThis, response);
                } else {
                    factoryThis.logToConsole(
                        'RPC error calling ' + method + ': ' +
                            goog.debug.expose(response.error),
                        'goofy-internal-error');
                }
            } else {
                if (callback) {
                    callback.call(factoryThis, response.result);
                }
            }
        },
        'POST', request);
};

/**
 * Sends a keepalive event if the web socket is open.
 */
cros.factory.Goofy.prototype.keepAlive = function() {
    if (this.ws.isOpen()) {
        this.sendEvent('goofy:keepalive', {'uuid': this.uuid});
    }
};

cros.factory.Goofy.prototype.LOAD_AVERAGE_FORMAT = (
    new goog.i18n.NumberFormat('0.00'));
cros.factory.Goofy.prototype.PERCENT_CPU_FORMAT = (
    new goog.i18n.NumberFormat('0.0%'));
cros.factory.Goofy.prototype.PERCENT_BATTERY_FORMAT = (
    new goog.i18n.NumberFormat('0%'));
/**
 * Gets the system status.
 */
cros.factory.Goofy.prototype.updateStatus = function() {
    this.sendRpc('get_system_status', [], function(status) {
        this.systemInfo['ips'] = status['ips'];
        this.setSystemInfo(this.systemInfo);

        function setValue(id, value) {
            var element = document.getElementById(id);
            goog.dom.classes.enable(element, 'goofy-value-known',
                                    value != null);
            goog.dom.getElementByClass('goofy-value', element
                                       ).innerHTML = value;
        }

        setValue('goofy-load-average',
                 status['load_avg'] ?
                 this.LOAD_AVERAGE_FORMAT.format(status['load_avg'][0]) :
                 null);

        if (this.lastStatus) {
            var lastCpu = goog.math.sum.apply(this, this.lastStatus['cpu']);
            var currentCpu = goog.math.sum.apply(this, status['cpu']);
            var lastIdle = this.lastStatus['cpu'][3];
            var currentIdle = status['cpu'][3];
            var deltaIdle = currentIdle - lastIdle;
            var deltaTotal = currentCpu - lastCpu;
            setValue('goofy-percent-cpu',
                     this.PERCENT_CPU_FORMAT.format(
                         (deltaTotal - deltaIdle) / deltaTotal));
        } else {
            setValue('goofy-percent-cpu', null);
        }

        var chargeIndicator = document.getElementById(
            'goofy-battery-charge-indicator');
        var percent = null;
        var batteryStatus = 'unknown';
        if (status.battery) {
            if (status.battery.fraction_full != null) {
                percent = this.PERCENT_BATTERY_FORMAT.format(
                    status.battery.fraction_full);
            }
            if (goog.array.contains(['Full', 'Charging', 'Discharging', 'Idle'],
                                    status.battery.status)) {
                batteryStatus = status.battery.status.toLowerCase();
            }
        }
        setValue('goofy-percent-battery', percent);
        goog.dom.classes.set(
            chargeIndicator, 'goofy-battery-' + batteryStatus);

        var temperatures = status['temperatures'];
        var mainTemperatureIndex = status['main_temperature_index'];
        var temp = null;
        // TODO(jsalz): Generalize to select and use the correct
        // temperature.
        if (mainTemperatureIndex != null &&
            temperatures && temperatures.length > mainTemperatureIndex &&
            temperatures[mainTemperatureIndex]) {
            temp = Math.round(temperatures[mainTemperatureIndex]) + '°C';
        }
        setValue('goofy-temperature', temp);

        var eth_indicator = document.getElementById('goofy-eth-indicator')
        goog.dom.classes.enable(eth_indicator, "goofy-eth-enabled",
                                status['eth_on'])
        var wlan_indicator = document.getElementById('goofy-wlan-indicator')
        goog.dom.classes.enable(wlan_indicator, "goofy-wlan-enabled",
                                status['wlan_on'])

        this.lastStatus = status;
    });
};

/**
 * Writes a message to the console log.
 * @param {string} message
 * @param {Object|Array.<string>|string=} opt_attributes attributes to add
 *     to the div element containing the log entry.
 */
cros.factory.Goofy.prototype.logToConsole = function(message, opt_attributes) {
    var div = goog.dom.createDom('div', opt_attributes);
    goog.dom.classes.add(div, 'goofy-log-line');
    div.appendChild(document.createTextNode(message));
    this.console.appendChild(div);
    // Scroll to bottom.  TODO(jsalz): Scroll only if already at the bottom,
    // or add scroll lock.
    var scrollPane = goog.dom.getAncestorByClass(this.console,
        'goog-splitpane-second-container');
    scrollPane.scrollTop = scrollPane.scrollHeight;
};

/**
 * Logs an "internal" message to the console (as opposed to a line from
 * console.log).
 */
cros.factory.Goofy.prototype.logInternal = function(message) {
    this.logToConsole(message, 'goofy-internal-log');
};

/**
 * Handles an event sends from the backend.
 * @param {string} jsonMessage the message as a JSON string.
 */
cros.factory.Goofy.prototype.handleBackendEvent = function(jsonMessage) {
    cros.factory.logger.info('Got message: ' + jsonMessage);
    var message = /** @type Object.<string, Object> */ (
        goog.json.unsafeParse(jsonMessage));

    if (message.type == 'goofy:hello') {
        if (this.uuid && message.uuid != this.uuid) {
            // The goofy process has changed; reload the page.
            cros.factory.logger.info('Incorrect UUID; reloading');
            window.location.reload();
            return;
        } else {
            this.uuid = message.uuid;
            // Send a keepAlive to confirm the UUID with the backend.
            this.keepAlive();
            // TODO(jsalz): Process version number information.
        }
    } else if (message.type == 'goofy:log') {
        this.logToConsole(message.message);
    } else if (message.type == 'goofy:state_change') {
        this.setTestState(message.path, message.state);
    } else if (message.type == 'goofy:init_test_ui') {
        var invocation = this.getOrCreateInvocation(
            message.test, message.invocation);
        if (invocation) {
            goog.dom.iframe.writeContent(
                invocation.iframe,
                /** @type {string} */(message['html']));
            this.updateCSSClassesInDocument(invocation.iframe.contentDocument);
        }

        // In the content window's evaluation context, add our keydown
        // listener.
        invocation.iframe.contentWindow.eval(
            'window.addEventListener("keydown", ' +
            'window.test.invocation.goofy.boundKeyListener)');
    } else if (message.type == 'goofy:set_html') {
        var invocation = this.getOrCreateInvocation(
            message.test, message.invocation);
        if (invocation) {
            if (message.id) {
                var element = invocation.iframe.contentDocument.getElementById(
                                                                    message.id);
                if (!message.append && element) {
                    element.innerHTML = '';
                }
                element.innerHTML += message['html'];
            } else {
                var body = invocation.iframe.contentDocument.body;
                if (body) {
                    if (!message.append) {
                        body.innerHTML = '';
                    }
                    body.innerHTML += message['html'];
                } else {
                    this.logToConsole(
                        'Test UI not initialized.', 'goofy-internal-error');
                }
            }
        }
    } else if (message.type == 'goofy:run_js') {
        var invocation = this.getOrCreateInvocation(
            message.test, message.invocation);
        if (invocation) {
            // We need to evaluate the code in the context of the content
            // window, but we also need to give it a variable.  Stash it
            // in the window and load it directly in the eval command.
            invocation.iframe.contentWindow.__goofy_args = message['args'];
            invocation.iframe.contentWindow.eval(
                'var args = window.__goofy_args;' +
                /** @type string */ (message['js']));
            delete invocation.iframe.contentWindow.__goofy_args;
        }
    } else if (message.type == 'goofy:call_js_function') {
        var invocation = this.getOrCreateInvocation(
            message.test, message.invocation);
        if (invocation) {
            var func = invocation.iframe.contentWindow.eval(message['name']);
            if (func) {
                func.apply(invocation.iframe.contentWindow, message['args']);
            } else {
                cros.factory.logger.severe('Unable to find function ' + func +
                                           ' in UI for test ' + message.test);
            }
        }
    } else if (message.type == 'goofy:destroy_test') {
        var invocation = this.invocations[message.invocation];
        if (invocation) {
            invocation.dispose();
        }
    } else if (message.type == 'goofy:system_info') {
        this.setSystemInfo(message['system_info']);
    } else if (message.type == 'goofy:pending_shutdown') {
        this.setPendingShutdown(
            /** @type {cros.factory.PendingShutdownEvent} */(message));
    } else if (message.type == 'goofy:update_notes') {
        this.sendRpc('get_shared_data', ['factory_note', true],
                     this.updateNote);
    }
};

goog.events.listenOnce(window, goog.events.EventType.LOAD, function() {
        window.goofy = new cros.factory.Goofy();
        window.goofy.init();
    });
