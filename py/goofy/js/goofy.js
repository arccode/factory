// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.Goofy');

goog.require('cros.factory.DeviceManager');
goog.require('cros.factory.DiagnosisTool');
goog.require('cros.factory.i18n');
goog.require('goog.Uri');
goog.require('goog.crypt');
goog.require('goog.crypt.Sha1');
goog.require('goog.crypt.base64');
goog.require('goog.date.Date');
goog.require('goog.date.DateTime');
goog.require('goog.debug.ErrorHandler');
goog.require('goog.debug.FancyWindow');
goog.require('goog.debug.Logger');
goog.require('goog.dom');
goog.require('goog.dom.classlist');
goog.require('goog.dom.iframe');
goog.require('goog.events');
goog.require('goog.events.EventHandler');
goog.require('goog.events.KeyCodes');
goog.require('goog.html.SafeHtml');
goog.require('goog.html.SafeStyle');
goog.require('goog.i18n.DateTimeFormat');
goog.require('goog.i18n.NumberFormat');
goog.require('goog.json');
goog.require('goog.math');
goog.require('goog.net.WebSocket');
goog.require('goog.net.XhrIo');
goog.require('goog.string');
goog.require('goog.style');
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

/**
 * @type {goog.debug.Logger}
 */
cros.factory.logger = goog.log.getLogger('cros.factory');

/**
 * @define {boolean} Whether to automatically collapse items once tests have
 *     completed.
 */
cros.factory.AUTO_COLLAPSE = false;

/**
 * Keep-alive interval for the WebSocket.  (Chrome times out
 * WebSockets every ~1 min, so 30 s seems like a good interval.)
 * @const
 * @type {number}
 */
cros.factory.KEEP_ALIVE_INTERVAL_MSEC = 30000;

/**
 * Interval at which to update system status.
 * @const
 * @type {number}
 */
cros.factory.SYSTEM_STATUS_INTERVAL_MSEC = 5000;

/**
 * Interval at which to try mounting the USB drive.
 * @const
 * @type {number}
 */
cros.factory.MOUNT_USB_DELAY_MSEC = 1000;

/**
 * Width of the control panel, as a fraction of the viewport size.
 * @type {number}
 */
cros.factory.CONTROL_PANEL_WIDTH_FRACTION = 0.21;

/**
 * Minimum width of the control panel, in pixels.
 * @type {number}
 */
cros.factory.CONTROL_PANEL_MIN_WIDTH = 275;

/**
 * Height of the log pane, as a fraction of the viewport size.
 * @type {number}
 */
cros.factory.LOG_PANE_HEIGHT_FRACTION = 0.2;

/**
 * Minimum height of the log pane, in pixels.
 * @type {number}
 */
cros.factory.LOG_PANE_MIN_HEIGHT = 170;

/**
 * Maximum size of a dialog (width or height) as a fraction of viewport size.
 * @type {number}
 */
cros.factory.MAX_DIALOG_SIZE_FRACTION = 0.75;

/**
 * Hover delay for a non-failing test.
 * @type {number}
 */
cros.factory.NON_FAILING_TEST_HOVER_DELAY_MSEC = 250;

/**
 * Factory Test Extension ID to support calling chrome API via RPC.
 * @type {string}
 */
cros.factory.EXTENSION_ID = 'pngocaclmlmihmhokaeejfiklacihcmb';

/**
 * @define {boolean} Whether to enable diagnosis tool or not.
 * The tool is still under development and is not ready for use yet.
 * TODO(bowgotsai): enable this when the tool is ready.
 */
cros.factory.ENABLE_DIAGNOSIS_TOOL = false;

/**
 * Maximum lines of console log to be shown in the UI.
 * @type {number}
 */
cros.factory.MAX_LINE_CONSOLE_LOG = 1024;

/**
 * Labels for items in system info.
 * @type {Array<{key: string, label: !goog.html.SafeHtml,
 *     transform: ?function(?string): !goog.html.SafeHtml}>}
 */
cros.factory.SYSTEM_INFO_LABELS = [
  {
    key: 'mlb_serial_number',
    label: cros.factory.i18n.i18nLabel('MLB Serial Number')
  },
  {key: 'serial_number', label: cros.factory.i18n.i18nLabel('Serial Number')},
  {key: 'stage', label: cros.factory.i18n.i18nLabel('Stage')}, {
    key: 'factory_image_version',
    label: cros.factory.i18n.i18nLabel('Factory Image Version')
  },
  {
    key: 'toolkit_version',
    label: cros.factory.i18n.i18nLabel('Factory Toolkit Version')
  },
  {
    key: 'release_image_version',
    label: cros.factory.i18n.i18nLabel('Release Image Version')
  },
  {key: 'wlan0_mac', label: cros.factory.i18n.i18nLabel('WLAN MAC')},
  {key: 'ips', label: cros.factory.i18n.i18nLabel('IP Addresses')},
  {key: 'kernel_version', label: cros.factory.i18n.i18nLabel('Kernel')},
  {key: 'architecture', label: cros.factory.i18n.i18nLabel('Architecture')},
  {key: 'ec_version', label: cros.factory.i18n.i18nLabel('EC')},
  {key: 'pd_version', label: cros.factory.i18n.i18nLabel('PD')}, {
    key: 'firmware_version',
    label: cros.factory.i18n.i18nLabel('Main Firmware')
  },
  {key: 'root_device', label: cros.factory.i18n.i18nLabel('Root Device')}, {
    key: 'factory_md5sum',
    label: cros.factory.i18n.i18nLabel('Factory MD5SUM'),
    transform: function(/** ?string */ value) {
      if (value == null) {
        return cros.factory.i18n.i18nLabel('(no update)');
      }
      return goog.html.SafeHtml.htmlEscape(value);
    }
  },
  {
    key: 'hwid_database_version',
    label: cros.factory.i18n.i18nLabel('HWID Database Version')
  }
];

/** @type {!goog.html.SafeHtml} */
cros.factory.UNKNOWN_LABEL = goog.html.SafeHtml.create(
    'span', {class: 'goofy-unknown'}, cros.factory.i18n.i18nLabel('Unknown'));

/**
 * An item in the test list.
 * @typedef {{path: string, label: cros.factory.i18n.TranslationDict,
 *     kbd_shortcut: string, disable_abort: boolean,
 *     subtests: !Array<cros.factory.TestListEntry>,
 *     state: cros.factory.TestState}}
 */
cros.factory.TestListEntry;

/**
 * A pending shutdown event.
 * @typedef {{delay_secs: number, time: number, operation: string,
 *     iteration: number, iterations: number, wait_shutdown_secs: number}}
 */
cros.factory.PendingShutdownEvent;

/**
 * Entry in test history returned by GetTestHistory.
 * @typedef {{init_time: number, start_time: number, end_time: number,
 *     status: string, path: string, invocation: string}}
 */
cros.factory.HistoryMetadata;

/**
 * Entry in test history.
 * @typedef {{metadata: cros.factory.HistoryMetadata, log: string}}
 */
cros.factory.HistoryEntry;

/**
 * TestState object in an event or RPC response.
 * @typedef {{status: string, skip: boolean, visible: boolean, count: number,
 *     error_msg: string, invocation: ?string, iterations_left: number,
 *     retries_left: number, shutdown_count: number}}
 */
cros.factory.TestState;

/**
 * Information about a test list.
 * @typedef {{id: string, name: cros.factory.i18n.TranslationDict,
 *     enabled: boolean}}
 */
cros.factory.TestListInfo;

/**
 * @typedef {{charge_manager: Object,
 *     battery: ?{charge_fraction: ?number, charge_state: ?string},
 *     fan_rpm: ?number, temperature: number, load_avg: Array<number>,
 *     cpu: ?Array<number>, ips: string, eth_on: boolean, wlan_on: boolean}}
 */
cros.factory.SystemStatus;

/**
 * Public API for tests.
 * @constructor
 * @param {cros.factory.Invocation} invocation
 */
cros.factory.Test = function(invocation) {
  /**
   * @type {cros.factory.Invocation}
   */
  this.invocation = invocation;

  /**
   * Map of char codes to handlers.  Null if not yet initialized.
   * @type {?Object<number, function(goog.events.KeyEvent)>}
   */
  this.keyHandlers = null;

  /**
   * Map of char codes to virtualkey buttons.
   * @type {!Object<number, !Element>}
   */
  this.keyButtons = {};
};

/**
 * Passes the test.
 * @export
 */
cros.factory.Test.prototype.pass = function() {
  this.invocation.goofy.sendEvent('goofy:end_test', {
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
 * @param {function(goog.events.KeyEvent)} handler the function to call when
 *     the key is pressed.
 * @export
 */
cros.factory.Test.prototype.bindKey = function(keyCode, handler) {
  if (!this.keyHandlers) {
    this.keyHandlers = {};
    // Set up the listener.
    goog.events.listen(
        this.invocation.iframe.contentWindow, goog.events.EventType.KEYUP,
        function(/** goog.events.KeyEvent */ event) {
          handler = this.keyHandlers[event.keyCode];
          if (handler) {
            handler(event);
          }
        },
        false, this);
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
};

/**
 * Unbinds all keys.
 * @export
 */
cros.factory.Test.prototype.unbindAllKeys = function() {
  // We don't actually remove the handler, just let it does nothing should be
  // good enough.
  this.keyHandlers = null;
};

/**
 * Add a virtualkey button.
 * @param {number} keyCode the keycode which handler should be triggered when
 *     clicking the button.
 * @param {cros.factory.i18n.TranslationDict} label label of the button.
 * @export
 */
cros.factory.Test.prototype.addVirtualkey = function(keyCode, label) {
  var container = this.invocation.iframe.contentDocument.getElementById(
      'virtualkey-button-container');
  // container may not exist if test is using non-standard template.
  if (container) {
    var html = cros.factory.i18n.i18nLabel(label);
    var button = goog.dom.createDom(
        'button', 'virtualkey-button', goog.dom.safeHtmlToNode(html));
    this.keyButtons[keyCode] = button;
    goog.events.listen(button, goog.events.EventType.CLICK, function(event) {
      var handler = this.keyHandlers[keyCode];
      if (handler) {
        // Not a key event, passing null in.
        handler(null);
      }
    }, false, this);
    container.appendChild(button);
  }
};

/**
 * Remove a virtualkey button.
 * @param {number} keyCode the keycode which button should be removed.
 * @export
 */
cros.factory.Test.prototype.removeVirtualkey = function(keyCode) {
  if (keyCode in this.keyButtons) {
    goog.dom.removeNode(this.keyButtons[keyCode]);
    delete this.keyButtons[keyCode];
  }
};

/**
 * Remove all virtualkey buttons.
 * @export
 */
cros.factory.Test.prototype.removeAllVirtualkeys = function() {
  goog.object.forEach(
      this.keyButtons, function(button) { goog.dom.removeNode(button); });
  this.keyButtons = {};
};

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
  goog.dom.classlist.enable(
      this.invocation.iframe, 'goofy-test-fullscreen', enable);
};

/**
 * UI for a single test invocation.
 * @constructor
 * @param {!cros.factory.Goofy} goofy
 * @param {string} path
 * @param {string} uuid
 * @param {?string} parentUuid
 */
cros.factory.Invocation = function(goofy, path, uuid, parentUuid) {
  /**
   * Reference to the Goofy object.
   * @type {!cros.factory.Goofy}
   */
  this.goofy = goofy;

  /**
   * @type {string}
   */
  this.path = path;

  /**
   * UUID of the invocation.
   * @type {string}
   */
  this.uuid = uuid;

  /**
   * UUID of the parent invocation; null if this is a top-level invocation.
   * @type {(string|null)}
   */
  this.parentUuid = parentUuid;

  /**
   * Sub-invocations of this invocation.
   * @type {Object<string, cros.factory.Invocation>}
   */
  this.subInvocations = {};

  /**
   * Test API for the invocation.
   */
  this.test = new cros.factory.Test(this);

  if (parentUuid) {
    /**
     * The iframe containing the test.
     * @type {HTMLIFrameElement}
     */
    this.iframe = goog.dom.iframe.createBlank(new goog.dom.DomHelper(document));
    goog.dom.classlist.add(this.iframe, 'goofy-test-iframe');
    goog.dom.classlist.enable(
        this.iframe, 'goofy-test-visible',
        goofy.pathTestMap[path].state.visible);
    document.getElementById('goofy-main').appendChild(this.iframe);
    this.iframe.contentWindow.$ = goog.bind(function(/** string */ id) {
      return this.iframe.contentDocument.getElementById(id);
    }, this);
    this.iframe.contentWindow.test = this.test;
    this.iframe.contentWindow.focus();
  }
};

/**
 * Returns state information for this invocation.
 * @return {cros.factory.TestState}
 */
cros.factory.Invocation.prototype.getState = function() {
  return this.goofy.pathTestMap[this.path].state;
};

/**
 * Disposes of the invocation (and destroys the iframe).
 */
cros.factory.Invocation.prototype.dispose = function() {
  for (var i in this.subInvocations) {
    this.subInvocations[i].dispose();
    this.subInvocations[i] = null;
  }
  if (this.iframe) {
    goog.log.info(cros.factory.logger, 'Cleaning up invocation ' + this.uuid);
    goog.dom.removeNode(this.iframe);
    this.iframe = null;
  }
  if (!this.parentUuid) {
    this.goofy.invocations[this.uuid] = null;
    goog.log.info(
        cros.factory.logger, 'Top-level invocation ' + this.uuid + ' disposed');
  }
};

/**
 * Types of notes.
 * @type {Array<{name: string, message: string}>}
 */
cros.factory.NOTE_LEVEL = [
  {name: 'INFO', message: 'Informative message only'},
  {name: 'WARNING', message: 'Displays a warning icon'},
  {name: 'CRITICAL', message: 'Testing is stopped indefinitely'}
];

/**
 * Constructor for Note.
 * @constructor
 * @param {string} name
 * @param {string} text
 * @param {number} timestamp
 * @param {string} level
 */
cros.factory.Note = function(name, text, timestamp, level) {
  this.name = name;
  this.text = text;
  this.timestamp = timestamp;
  this.level = level;
};

/**
 * UI for displaying critical factory notes.
 * @constructor
 * @param {cros.factory.Goofy} goofy
 * @param {Array<cros.factory.Note>} notes
 */
cros.factory.CriticalNoteDisplay = function(goofy, notes) {
  this.goofy = goofy;
  this.div = goog.dom.createDom('div', 'goofy-fullnote-display-outer');
  document.getElementById('goofy-main').appendChild(this.div);

  var innerDiv = goog.dom.createDom('div', 'goofy-fullnote-display-inner');
  this.div.appendChild(innerDiv);

  var titleDiv = goog.dom.createDom('div', 'goofy-fullnote-title');
  var titleImg = goog.dom.createDom(
      'img', {class: 'goofy-fullnote-logo', src: '/images/warning.svg'});
  titleDiv.appendChild(titleImg);
  titleDiv.appendChild(
      cros.factory.i18n.i18nLabelNode('Factory tests stopped'));
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
   * @type {goog.net.WebSocket}
   */
  this.ws = new goog.net.WebSocket();

  /**
   * Whether we have opened the WebSocket yet.
   * @type {boolean}
   */
  this.wsOpened = false;

  /**
   * The UUID that we received from Goofy when starting up.
   * @type {?string}
   */
  this.uuid = null;

  /**
   * The currently visible context menu, if any.
   * @type {goog.ui.PopupMenu}
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
   * @type {!Array<goog.ui.AdvancedTooltip>}
   */
  this.tooltips = [];

  /**
   * The test tree.
   * @type {!goog.ui.tree.TreeControl}
   */
  this.testTree = new goog.ui.tree.TreeControl('Tests');
  this.testTree.setShowRootNode(false);
  this.testTree.setShowLines(false);

  /**
   * A map from test path to the tree node for each test.
   * @type {Object<string, !goog.ui.tree.BaseNode>}
   */
  this.pathNodeMap = {};

  /**
   * A map from test path to the entry in the test list for that test.
   * @type {Object<string, !cros.factory.TestListEntry>}
   */
  this.pathTestMap = {};

  /**
   * A map from test path to the tree node html id for external reference.
   * @type {Object<string, string>}
   */
  this.pathNodeIdMap = {};

  /**
   * Whether Chinese mode is currently enabled.
   *
   * TODO(jsalz): Generalize this to multiple languages (but this isn't
   * really necessary now).
   *
   * @type {boolean}
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
   * @type {Object<string, cros.factory.Invocation>}
   */
  this.invocations = {};

  /**
   * Eng mode prompt.
   * @type {goog.ui.Dialog}
   */
  this.engineeringModeDialog = null;

  /**
   * Shutdown prompt dialog.
   * @type {goog.ui.Dialog}
   */
  this.shutdownDialog = null;

  /**
   * Visible dialogs.
   * @type {Array<goog.ui.Dialog>}
   */
  this.dialogs = [];

  /**
   * Whether eng mode is enabled.
   * @type {boolean}
   */
  this.engineeringMode = false;

  /**
   * Last system info received.
   * @type {Object<string, string>}
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
   * @type {Array<cros.factory.TestListInfo>}
   */
  this.testLists = [];

  /**
   * Whether any automation mode is enabled.
   * @type {boolean}
   */
  this.automationEnabled = false;

  /**
   * All current notes.
   * @type {Array<cros.factory.Note>}
   */
  this.notes = null;

  /**
   * The display for notes.
   * @type {cros.factory.CriticalNoteDisplay}
   */
  this.noteDisplay = null;

  /**
   * The DOM element for console.
   * @type {Element}
   */
  this.console = null;

  /**
   * The DOM element for terminal window.
   * @type {Element}
   */
  this.terminal_win = null;

  /**
   * The WebSocket for terminal window.
   * @type {WebSocket}
   */
  this.terminal_sock = null;

  /**
   * @type {?cros.factory.SystemStatus}
   */
  this.lastStatus = null;

  // Set up magic keyboard shortcuts.
  goog.events.listen(
      window, goog.events.EventType.KEYDOWN, this.keyListener, true, this);

  this.deviceManager = new cros.factory.DeviceManager(this);
  if (cros.factory.ENABLE_DIAGNOSIS_TOOL) {
    this.diagnosisTool = new cros.factory.DiagnosisTool(this);
  }
};

/**
 * Sets the title of a modal dialog.
 * @param {goog.ui.Dialog} dialog
 * @param {string|!goog.html.SafeHtml} title
 */
cros.factory.Goofy.setDialogTitle = function(dialog, title) {
  goog.dom.safe.setInnerHtml(
      /** @type {!Element} */ (dialog.getTitleTextElement()),
      goog.html.SafeHtml.htmlEscapePreservingNewlines(title));
};

/**
 * Sets the content of a modal dialog.
 * @param {goog.ui.Dialog} dialog
 * @param {string|!goog.html.SafeHtml} content
 */
cros.factory.Goofy.setDialogContent = function(dialog, content) {
  dialog.setSafeHtmlContent(
      goog.html.SafeHtml.htmlEscapePreservingNewlines(content));
};

/**
 * Event listener for Ctrl-Alt-keypress.
 * @param {goog.events.KeyEvent} event
 */
cros.factory.Goofy.prototype.keyListener = function(event) {
  // Prevent backspace, alt+left, or alt+right to do page navigation.
  if ((event.keyCode === goog.events.KeyCodes.BACKSPACE &&
       event.target.nodeName === 'BODY') ||
      ((event.keyCode === goog.events.KeyCodes.LEFT ||
        event.keyCode === goog.events.KeyCodes.RIGHT) &&
       event.altKey)) {
    event.preventDefault();
  }

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
  if (!this.engineeringMode && event.altKey && event.platformModifierKey) {
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
      mainComponent, consoleComponent, goog.ui.SplitPane.Orientation.VERTICAL);

  mainAndConsole.setInitialSize(
      viewportSize.height -
      Math.max(
          cros.factory.LOG_PANE_MIN_HEIGHT,
          viewportSize.height * cros.factory.LOG_PANE_HEIGHT_FRACTION));

  goog.debug.catchErrors(
      goog.bind(
          function(
              /** {fileName: string, line: string, message: string} */ info) {
            try {
              this.logToConsole(
                  'JavaScript error (' + info.fileName + ', line ' + info.line +
                      '): ' + info.message,
                  'goofy-internal-error');
            } catch (e) {
              // Oof... error while logging an error!  Maybe the DOM
              // isn't set up properly yet; just ignore.
            }
          },
          this),
      false);

  var controlComponent = new goog.ui.Component();
  var topSplitPane = new goog.ui.SplitPane(
      controlComponent, mainAndConsole,
      goog.ui.SplitPane.Orientation.HORIZONTAL);
  topSplitPane.setInitialSize(Math.max(
      cros.factory.CONTROL_PANEL_MIN_WIDTH,
      viewportSize.width * cros.factory.CONTROL_PANEL_WIDTH_FRACTION));
  // Decorate the uppermost splitpane and disable its context menu.
  var topSplitPaneElement = document.getElementById('goofy-splitpane');
  topSplitPane.decorate(topSplitPaneElement);
  // Disable context menu except in engineering mode.
  goog.events.listen(
      topSplitPaneElement, goog.events.EventType.CONTEXTMENU,
      function(/** goog.events.Event */ event) {
        if (!this.engineeringMode) {
          event.stopPropagation();
          event.preventDefault();
        }
      },
      false, this);

  mainComponent.getElement().id = 'goofy-main';
  mainComponent.getElement().innerHTML =
      '<img id="goofy-main-logo" src="/images/logo256.png">';
  consoleComponent.getElement().id = 'goofy-console';
  this.console = consoleComponent.getElement();
  this.main = mainComponent.getElement();

  var propagate = true;
  goog.events.listen(
      topSplitPane, goog.ui.Component.EventType.CHANGE, function(event) {
        if (!propagate) {
          // Prevent infinite recursion
          return;
        }

        propagate = false;
        mainAndConsole.setFirstComponentSize(
            mainAndConsole.getFirstComponentSize());
        propagate = true;

        var rect = mainComponent.getElement().getBoundingClientRect();
        this.sendRpc(
            'get_shared_data', ['ui_scale_factor'],
            function(/** number */ uiScaleFactor) {
              this.sendRpc('set_shared_data', [
                'test_widget_size',
                [rect.width * uiScaleFactor, rect.height * uiScaleFactor],
                'test_widget_position',
                [rect.left * uiScaleFactor, rect.top * uiScaleFactor]
              ]);
            });
      }, false, this);
  mainAndConsole.setFirstComponentSize(mainAndConsole.getFirstComponentSize());
  goog.events.listen(window, goog.events.EventType.RESIZE, function(event) {
    var viewportSize =
        goog.dom.getViewportSize(goog.dom.getWindow(document) || window);
    if (this.automationEnabled) {
      var indicator = document.getElementById('goofy-automation-div');
      viewportSize.height -= indicator.offsetHeight;
    }
    topSplitPane.setSize(viewportSize);
  }, false, this);

  // Whenever we get focus, try to focus any visible iframe (if no modal
  // dialog is visible).
  goog.events.listen(window, goog.events.EventType.FOCUS, function() {
    goog.Timer.callOnce(this.focusInvocation, 0, this);
  }, false, this);
};

/**
 * Returns focus to any visible invocation.
 */
cros.factory.Goofy.prototype.focusInvocation = function() {
  if (goog.array.find(
          this.dialogs, function(dialog) { return dialog.isVisible(); })) {
    // Don't divert focus, since a dialog is visible.
    return;
  }

  goog.object.forEach(this.invocations, function(i) {
    if (i && i.iframe && i.getState().visible) {
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
  goog.events.listen(
      this.ws, goog.net.WebSocket.EventType.OPENED, function(event) {
        this.logInternal('Connection to Goofy opened.');
        this.wsOpened = true;
      }, false, this);
  goog.events.listen(
      this.ws, goog.net.WebSocket.EventType.ERROR, function(event) {
        this.logInternal('Error connecting to Goofy.');
      }, false, this);
  goog.events.listen(
      this.ws, goog.net.WebSocket.EventType.CLOSED, function(event) {
        if (this.wsOpened) {
          this.logInternal('Connection to Goofy closed.');
          this.wsOpened = false;
        }
      }, false, this);
  goog.events.listen(
      this.ws, goog.net.WebSocket.EventType.MESSAGE,
      function(/** goog.net.WebSocket.MessageEvent */ event) {
        this.handleBackendEvent(event.message);
      },
      false, this);
  window.setInterval(
      goog.bind(this.keepAlive, this), cros.factory.KEEP_ALIVE_INTERVAL_MSEC);
  window.setInterval(
      goog.bind(this.updateStatus, this),
      cros.factory.SYSTEM_STATUS_INTERVAL_MSEC);
  this.updateStatus();
  this.ws.open('ws://' + window.location.host + '/event');
};

/**
 * Waits for the Goofy backend to be ready, and then starts UI.
 */
cros.factory.Goofy.prototype.preInit = function() {
  this.sendRpc('IsReadyForUIConnection', [], function(/** boolean */ is_ready) {
    if (is_ready) {
      this.init();
    } else {
      window.console.log('Waiting for the Goofy backend to be ready...');
      var goofyThis = this;
      window.setTimeout(function() { goofyThis.preInit(); }, 500);
    }
  });
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
      function(/** goog.events.KeyEvent */ event) {
        if (event.altKey || event.ctrlKey) {
          this.handleShortcut(String.fromCharCode(event.keyCode));
        }
      },
      false, this);

  this.sendRpc(
      'GetTestLists', [],
      function(/** Array<cros.factory.TestListInfo> */ testLists) {
        this.testLists = testLists;
      });
  this.sendRpc(
      'GetTestList', [], function(/** cros.factory.TestListEntry */ testList) {
        this.setTestList(testList);
        this.initWebSocket();
      });
  this.sendRpc('get_shared_data', ['system_info'], this.setSystemInfo);
  this.sendRpc('get_shared_data', ['factory_note', true], this.updateNote);
  this.sendRpc(
      'get_shared_data', ['test_list_options'],
      function(/** Object<string, ?string> */ options) {
        this.engineeringPasswordSHA1 = options['engineering_password_sha1'];
        // If no password, enable eng mode, and don't
        // show the 'disable' link, since there is no way to
        // enable it.
        goog.style.setElementShown(
            document.getElementById('goofy-disable-engineering-mode'),
            this.engineeringPasswordSHA1 != null);
        this.setEngineeringMode(this.engineeringPasswordSHA1 == null);
      });
  this.sendRpc(
      'get_shared_data', ['startup_error'],
      function(/** string */ error) {
        var alertHtml = goog.html.SafeHtml.concat(
            cros.factory.i18n.i18nLabel(
                'An error occurred while starting the factory test system\n' +
                'Factory testing cannot proceed.'),
            goog.html.SafeHtml.create(
                'div', {class: 'goofy-startup-error'}, error));
        this.alert(alertHtml);
      },
      function() {
        // Unable to retrieve the key; that's fine, no startup error!
      });
  this.sendRpc(
      'get_shared_data', ['automation_mode'],
      function(/** string */ mode) { this.setAutomationMode(mode); });

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
      goog.events.EventType.CLICK, function(event) {
        this.zhMode = !this.zhMode;
        this.updateCSSClasses();
        this.sendRpc('set_shared_data', ['ui_lang', this.zhMode ? 'zh' : 'en']);
      }, false, this);

  this.updateCSSClasses();
  this.sendRpc('get_shared_data', ['ui_lang'], function(/** string */ lang) {
    this.zhMode = lang == 'zh';
    this.updateCSSClasses();
  });
};

/**
 * Sets up the automation mode indicator bar.
 *
 * @param {string} mode
 */
cros.factory.Goofy.prototype.setAutomationMode = function(mode) {
  if (mode != 'NONE') {
    this.automationEnabled = true;
    this.sendRpc(
        'get_shared_data', ['automation_mode_prompt'],
        function(/** string */ prompt) {
          document.getElementById('goofy-automation-div').innerHTML = prompt;
        });
  }
  this.updateCSSClasses();
  goog.events.fireListeners(window, goog.events.EventType.RESIZE, false, null);
};

/**
 * Gets an invocation for a test (creating it if necessary).
 *
 * @param {string} path
 * @param {string} invocationUuid
 * @param {string} parentUuid
 * @return {?cros.factory.Invocation} the invocation, or null if the invocation
 *     has already been created and deleted.
 */
cros.factory.Goofy.prototype.getOrCreateInvocation = function(
    path, invocationUuid, parentUuid) {
  if (invocationUuid in this.invocations) {
    return this.invocations[invocationUuid];
  }

  if (!(parentUuid in this.invocations)) {
    cros.factory.logger.info(
        'Creating top-level invocation ' +
        '(invocation ' + parentUuid + ')');
    this.invocations[parentUuid] =
        new cros.factory.Invocation(this, path, parentUuid, null);
  }

  var subInvocations = this.invocations[parentUuid].subInvocations;
  if (!(invocationUuid in subInvocations)) {
    cros.factory.logger.info(
        'Creating UI for test ' + path + ' (invocation ' + invocationUuid +
        ')');
    subInvocations[invocationUuid] =
        new cros.factory.Invocation(this, path, invocationUuid, parentUuid);
  }
  return subInvocations[invocationUuid];
};

/**
 * Updates language classes in a document based on the current value of
 * zhMode.
 * @param {Document} doc
 */
cros.factory.Goofy.prototype.updateCSSClassesInDocument = function(doc) {
  if (doc.body) {
    goog.dom.classlist.enable(doc.body, 'goofy-lang-en-US', !this.zhMode);
    goog.dom.classlist.enable(doc.body, 'goofy-lang-zh-CN', this.zhMode);
    goog.dom.classlist.enable(
        doc.body, 'goofy-engineering-mode', this.engineeringMode);
    goog.dom.classlist.enable(
        doc.body, 'goofy-operator-mode', !this.engineeringMode);
    goog.dom.classlist.enable(
        doc.body, 'goofy-enable-automation', this.automationEnabled);
    goog.dom.classlist.enable(
        document.getElementById('goofy-terminal'), 'goofy-engineering-mode',
        this.engineeringMode);
  }
};

/**
 * Updates language classes in the UI based on the current value of
 * zhMode.
 */
cros.factory.Goofy.prototype.updateCSSClasses = function() {
  this.updateCSSClassesInDocument.call(this, document);
  /**
   * @this {cros.factory.Goofy}
   * @param {Object<string, cros.factory.Invocation>} invocations
   */
  var recursiveUpdate = function(invocations) {
    goog.object.forEach(invocations, function(i) {
      if (i && i.iframe) {
        this.updateCSSClassesInDocument.call(this, i.iframe.contentDocument);
      }
      if (i && i.subInvocations) {
        recursiveUpdate.call(this, i.subInvocations);
      }
    }, this);
  };
  recursiveUpdate.call(this, this.invocations);
};

/**
 * Updates the system info tooltip.
 * @param {Object<string, string>} systemInfo
 */
cros.factory.Goofy.prototype.setSystemInfo = function(systemInfo) {
  this.systemInfo = systemInfo;

  var rows = [];
  goog.array.forEach(cros.factory.SYSTEM_INFO_LABELS, function(item) {
    var value = systemInfo[item.key];
    var html;
    if (item.transform) {
      html = item.transform(value);
    } else {
      html = value == undefined ? cros.factory.UNKNOWN_LABEL : value;
    }
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create('th', {}, item.label),
      goog.html.SafeHtml.create('td', {}, html)
    ]));
  });
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('Host Based')),
    goog.html.SafeHtml.create('td', {}, '1')
  ]));
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('System time')),
    goog.html.SafeHtml.create('td', {id: 'goofy-time'})
  ]));

  var table =
      goog.html.SafeHtml.create('table', {id: 'goofy-system-info'}, rows);
  this.infoTooltip.setSafeHtml(table);
  this.updateTime();

  goog.dom.classlist.enable(
      document.body, 'goofy-update-available', !!systemInfo['update_md5sum']);
};

/**
 * Updates notes.
 * @param {Array<cros.factory.Note>} notes
 */
cros.factory.Goofy.prototype.updateNote = function(notes) {
  this.notes = notes;
  var currentLevel = notes ? notes[notes.length - 1].level : '';

  goog.array.forEach(cros.factory.NOTE_LEVEL, function(lvl) {
    goog.dom.classlist.enable(
        document.getElementById('goofy-logo'),
        'goofy-note-' + lvl.name.toLowerCase(), currentLevel == lvl.name);
  });

  if (this.noteDisplay) {
    this.noteDisplay.dispose();
    this.noteDisplay = null;
  }

  if (notes && notes.length > 0 &&
      notes[notes.length - 1].level == 'CRITICAL') {
    this.noteDisplay = new cros.factory.CriticalNoteDisplay(this, notes);
  }
};

/** @type {goog.i18n.DateTimeFormat} */
cros.factory.Goofy.MDHMS_TIME_FORMAT =
    new goog.i18n.DateTimeFormat('MM/dd HH:mm:ss');

/**
 * Gets factory notes list.
 * @return {!goog.html.SafeHtml}
 */
cros.factory.Goofy.prototype.getNotesView = function() {
  var rows = [];
  goog.array.forEachRight(this.notes, function(item) {
    var d = new Date(0);
    d.setUTCSeconds(item.timestamp);
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create(
          'td', {}, cros.factory.Goofy.MDHMS_TIME_FORMAT.format(d)),
      goog.html.SafeHtml.create('th', {}, item.name),
      goog.html.SafeHtml.create('td', {}, item.text)
    ]));
  });
  var table = goog.html.SafeHtml.create('table', {id: 'goofy-note-list'}, rows);
  return table;
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

  var viewSize =
      goog.dom.getViewportSize(goog.dom.getWindow(document) || window);
  var maxWidth = viewSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
  var maxHeight = viewSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;

  dialog.setTitle('Factory Notes');
  var style = goog.html.SafeStyle.create(
      {'max-width': maxWidth.toString(), 'max-height': maxHeight.toString()});
  cros.factory.Goofy.setDialogContent(
      dialog, goog.html.SafeHtml.create(
                  'div', {class: 'goofy-note-container', style: style},
                  this.getNotesView()));
  dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
  dialog.setVisible(true);
};

/**
 * Updates the current time.
 */
cros.factory.Goofy.prototype.updateTime = function() {
  var element = document.getElementById('goofy-time');
  if (element) {
    element.innerHTML = new goog.date.DateTime().toUTCIsoString(true) + ' UTC';
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
      (/** @type {!Element} */ (inputs[0])).focus();
    }
  });
  goog.events.listen(dialog, goog.ui.Component.EventType.HIDE, function() {
    goog.Timer.callOnce(this.focusInvocation, 0, this);
    goog.array.remove(this.dialogs, dialog);
  }, false, this);
};

/**
 * Displays an alert.
 * @param {string|!goog.html.SafeHtml} message
 */
cros.factory.Goofy.prototype.alert = function(message) {
  var dialog = new goog.ui.Dialog();
  this.registerDialog(dialog);
  dialog.setTitle('Alert');
  dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
  cros.factory.Goofy.setDialogContent(dialog, message);
  dialog.setVisible(true);
  goog.dom.classlist.add(dialog.getElement(), 'goofy-alert');
};

/**
 * Centers an element over the console.
 * @param {Element} element
 */
cros.factory.Goofy.prototype.positionOverConsole = function(element) {
  var consoleBounds =
      goog.style.getBounds(/** @type {Element} */ (this.console.parentNode));
  var size = goog.style.getSize(element);
  goog.style.setPosition(
      element, consoleBounds.left + consoleBounds.width / 2 - size.width / 2,
      consoleBounds.top + consoleBounds.height / 2 - size.height / 2);
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
      'Password', '', goog.bind(function(/** string */ text) {
        if (!text) {
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
  goog.dom.classlist.add(
      this.engineeringModeDialog.getElement(), 'goofy-engineering-mode-dialog');
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
 * @param {?cros.factory.PendingShutdownEvent} shutdownInfo
 */
cros.factory.Goofy.prototype.setPendingShutdown = function(shutdownInfo) {
  if (this.shutdownDialog) {
    this.shutdownDialog.setVisible(false);
    this.shutdownDialog.dispose();
    this.shutdownDialog = null;
  }
  if (!shutdownInfo || !shutdownInfo.operation) {
    return;
  }

  var _ = cros.factory.i18n.translation;
  var action =
      shutdownInfo.operation == 'reboot' ? _('Rebooting') : _('Shutting down');

  var timesText = shutdownInfo.iterations == 1 ?
      _('once') :
      cros.factory.i18n.stringFormat(
          _('{count} of {total} times'),
          {count: shutdownInfo.iteration, total: shutdownInfo.iterations});

  this.shutdownDialog = new goog.ui.Dialog();
  this.registerDialog(this.shutdownDialog);
  var messageDiv = goog.dom.createDom('div');
  goog.dom.appendChild(this.shutdownDialog.getContentElement(), messageDiv);

  var progressBar = new goog.ui.ProgressBar();
  progressBar.render(this.shutdownDialog.getContentElement());

  var startTime = new Date().getTime() / 1000.0;
  var endTime = new Date().getTime() / 1000.0 + shutdownInfo.delay_secs;
  var shutdownDialog = this.shutdownDialog;

  /** @this {cros.factory.Goofy} */
  function tick() {
    var now = new Date().getTime() / 1000.0;

    if (endTime > now) {
      var fraction = (now - startTime) / (endTime - startTime);
      progressBar.setValue(goog.math.clamp(fraction, 0, 1) * 100);

      var secondsLeft = 1 + Math.floor(Math.max(0, endTime - now));
      goog.dom.safe.setInnerHtml(
          messageDiv,
          cros.factory.i18n.i18nLabel(
              '{action} in {seconds_left} seconds ({times_text}).\n' +
                  'To cancel, press the Escape key.',
              {
                action: action,
                times_text: timesText,
                seconds_left: secondsLeft
              }));
    } else if (now - endTime < shutdownInfo.wait_shutdown_secs) {
      cros.factory.Goofy.setDialogContent(
          shutdownDialog, cros.factory.i18n.i18nLabel('Shutting down...'));
    } else {
      this.setPendingShutdown(null);
      return;
    }
  }
  tick.call(this);

  var timer = new goog.Timer(20);
  goog.events.listen(timer, goog.Timer.TICK, tick, false, this);
  timer.start();

  goog.events.listen(
      this.shutdownDialog, goog.ui.PopupBase.EventType.BEFORE_HIDE,
      function(event) { timer.dispose(); });

  goog.events.listen(
      this.shutdownDialog.getElement(),
      goog.events.EventType.KEYDOWN, function(/** goog.events.KeyEvent */ e) {
        if (e.keyCode == goog.events.KeyCodes.ESC) {
          this.cancelShutdown();
        }
      }, false, this);

  var buttonSet = new goog.ui.Dialog.ButtonSet();
  buttonSet.set(
      goog.ui.Dialog.DefaultButtonKeys.CANCEL,
      cros.factory.i18n.i18nLabelNode('Cancel'), true, true);
  this.shutdownDialog.setButtonSet(buttonSet);

  goog.events.listen(
      this.shutdownDialog,
      goog.ui.Dialog.EventType.SELECT, function(/** goog.ui.Dialog.Event */ e) {
        if (e.key == goog.ui.Dialog.DefaultButtonKeys.CANCEL) {
          this.cancelShutdown();
        }
      }, false, this);

  this.shutdownDialog.setHasTitleCloseButton(false);
  this.shutdownDialog.setEscapeToCancel(false);
  goog.dom.classlist.add(
      this.shutdownDialog.getElement(), 'goofy-shutdown-dialog');
  this.shutdownDialog.setVisible(true);
  goog.events.listen(
      this.shutdownDialog.getElement(),
      goog.events.EventType.BLUR, function(event) {
        goog.Timer.callOnce(
            goog.bind(this.shutdownDialog.focus, this.shutdownDialog));
      }, false, this);
};

/**
 * Cancels a pending shutdown.
 */
cros.factory.Goofy.prototype.cancelShutdown = function() {
  this.sendEvent('goofy:cancel_shutdown', {});
  // Wait for Goofy to reset the pending_shutdown data.
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
  this.sendEvent(
      'goofy:run_tests_with_status',
      {'status': ['UNTESTED', 'ACTIVE', 'FAILED', 'FAILED_AND_WAIVED']});
};

/**
 * Makes a menu item for a context-sensitive menu.
 *
 * @param {string|cros.factory.i18n.TranslationDict} text the text to
 *     display for non-leaf node.
 * @param {string|cros.factory.i18n.TranslationDict} text_leaf the text to
 *     display for leaf node.
 * @param {number} count the number of tests.
 * @param {cros.factory.TestListEntry} test the root node containing the tests.
 * @param {function(this:cros.factory.Goofy, goog.events.Event)}
 *     handler the handler function (see goog.events.listen).
 * @return {!goog.ui.MenuItem}
 */
cros.factory.Goofy.prototype.makeMenuItem = function(
    text, text_leaf, count, test, handler) {
  var test_label = cros.factory.i18n.translated(test.label);

  var item = new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(
      test.subtests.length == 0 ? text_leaf : text,
      {count: count, test: test_label}));
  item.setEnabled(count != 0);
  goog.events.listen(
      item, goog.ui.Component.EventType.ACTION, handler, true, this);
  return item;
};

/**
 * Returns true if all tests in the test lists before a given test have been
 * run.
 * @param {cros.factory.TestListEntry} test
 * @return {boolean}
 */
cros.factory.Goofy.prototype.allTestsRunBefore = function(test) {
  var root = this.pathTestMap[''];

  // Create a stack containing only the root node, and walk through
  // it depth-first.  (Use a stack rather than recursion since we
  // want to be able to bail out easily when we hit 'test' or an
  // incomplete test.)
  var /** Array<!cros.factory.TestListEntry> */ stack = [root];
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
      if (item.state.status == 'ACTIVE' || item.state.status == 'UNTESTED') {
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
 * @param {Array<goog.ui.Control>=} extraItems items to prepend to the
 *     menu.
 * @return {boolean}
 */
cros.factory.Goofy.prototype.showTestPopup = function(
    path, labelElement, extraItems) {
  var test = this.pathTestMap[path];
  var _ = cros.factory.i18n.translation;

  if (path == this.lastContextMenuPath &&
      (goog.now() - this.lastContextMenuHideTime <
       goog.ui.PopupBase.DEBOUNCE_DELAY_MS)) {
    // We just hid it; don't reshow.
    return false;
  }

  // If it's a leaf node, and it's the active but not the visible
  // test, ask the backend to make it visible.
  if (test.state.status == 'ACTIVE' &&
      !/** @type {boolean} */ (test.state.visible) && !test.subtests.length) {
    this.sendEvent('goofy:set_visible_test', {path: path});
  }

  // Hide all tooltips so that they don't fight with the context menu.
  this.hideTooltips();

  var menu = this.contextMenu = new goog.ui.PopupMenu();
  function addSeparator() {
    if (menu.getChildCount() &&
        !(menu.getChildAt(menu.getChildCount() - 1) instanceof
          goog.ui.MenuSeparator)) {
      menu.addChild(new goog.ui.MenuSeparator(), true);
    }
  }

  this.lastContextMenuPath = path;

  var numLeaves = 0;
  var /** Object<string, number> */ numLeavesByStatus = {};
  var allPaths = [];
  var activeAndDisableAbort = false;

  function countLeaves(/** cros.factory.TestListEntry */ test) {
    allPaths.push(test.path);
    goog.array.forEach(test.subtests, countLeaves);

    if (!test.subtests.length) {
      ++numLeaves;
      numLeavesByStatus[test.state.status] =
          1 + (numLeavesByStatus[test.state.status] || 0);
      // If there is any subtest that is active and can not be aborted,
      // this test can not be aborted.
      if (test.state.status == 'ACTIVE' && test.disable_abort) {
        activeAndDisableAbort = true;
      }
    }
  }
  countLeaves(test);

  if (this.noteDisplay) {
    var item = new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(
        'Critical factory note; cannot run tests'));
    menu.addChild(item, true);
    item.setEnabled(false);
  } else if (!this.engineeringMode && !this.allTestsRunBefore(test)) {
    var item = new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(
        'Not in engineering mode; cannot skip tests'));
    menu.addChild(item, true);
    item.setEnabled(false);
  } else {
    if (this.engineeringMode ||
        (!test.subtests.length && test.state.status != 'PASSED')) {
      // Allow user to restart all tests under a particular node if
      // (a) in engineering mode, or (b) if this is a single non-passed
      // test.  If neither of these is true, it's too easy to
      // accidentally re-run a bunch of tests and wipe their state.
      var allUntested = numLeavesByStatus['UNTESTED'] == numLeaves;
      /**
       * @this {cros.factory.Goofy}
       * @param {goog.events.Event} event
       */
      var handler = function(event) {
        this.sendEvent('goofy:restart_tests', {path: path});
      };
      if (allUntested) {
        menu.addChild(
            this.makeMenuItem(
                _('Run all {count} tests in "{test}"'), _('Run test "{test}"'),
                numLeaves, test, handler),
            true);
      } else {
        menu.addChild(
            this.makeMenuItem(
                _('Restart all {count} tests in "{test}"'),
                _('Restart test "{test}"'), numLeaves, test, handler),
            true);
      }
    }
    if (test.subtests.length) {
      // Only show for parents.
      menu.addChild(
          this.makeMenuItem(
              _('Restart {count} tests in "{test}" that have not passed'), '',
              (numLeavesByStatus['UNTESTED'] || 0) +
                  (numLeavesByStatus['ACTIVE'] || 0) +
                  (numLeavesByStatus['FAILED'] || 0),
              test,
              function(event) {
                this.sendEvent('goofy:run_tests_with_status', {
                  'status':
                      ['UNTESTED', 'ACTIVE', 'FAILED', 'FAILED_AND_WAIVED'],
                  'path': path
                });
              }),
          true);
    }
    if (this.engineeringMode) {
      menu.addChild(
          this.makeMenuItem(
              _('Clear status of {count} tests in "{test}"'),
              _('Clear status of test "{test}"'), numLeaves, test,
              function(event) {
                this.sendEvent('goofy:clear_state', {path: path});
              }),
          true);
    }
    if (this.engineeringMode && test.subtests.length) {
      menu.addChild(
          this.makeMenuItem(
              _('Run {count} untested tests in "{test}"'), '',
              (numLeavesByStatus['UNTESTED'] || 0) +
                  (numLeavesByStatus['ACTIVE'] || 0),
              test,
              function(event) {
                this.sendEvent('goofy:auto_run', {path: path});
              }),
          true);
    }
  }
  addSeparator();

  var stopAllItem =
      new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode('Stop all tests'));
  stopAllItem.setEnabled(numLeavesByStatus['ACTIVE'] > 0);
  menu.addChild(stopAllItem, true);
  goog.events.listen(
      stopAllItem, goog.ui.Component.EventType.ACTION, function(event) {
        this.sendEvent(
            'goofy:stop', {'fail': true, 'reason': 'Operator requested abort'});
      }, true, this);

  // When there is any active test, enable abort item in menu
  // if goofy is in engineering mode or there is no
  // active subtest with disable_abort=true.
  if (numLeavesByStatus['ACTIVE'] &&
      (this.engineeringMode || !activeAndDisableAbort)) {
    menu.addChild(
        this.makeMenuItem(
            _('Abort {count} active tests in "{test}" and continue testing'),
            _('Abort active test "{test}" and continue testing'),
            numLeavesByStatus['ACTIVE'] || 0, test,
            function(event) {
              this.sendEvent('goofy:stop', {
                'path': path,
                'fail': true,
                'reason': 'Operator requested abort'
              });
            }),
        true);
  }

  if (this.engineeringMode && !test.subtests.length) {
    addSeparator();
    menu.addChild(this.createViewLogMenu(path), true);
  }

  if (extraItems && extraItems.length) {
    addSeparator();
    goog.array.forEach(
        extraItems, function(item) { menu.addChild(item, true); });
  }

  menu.render(document.body);
  menu.showAtElement(
      labelElement, goog.positioning.Corner.BOTTOM_LEFT,
      goog.positioning.Corner.TOP_LEFT);
  goog.events.listen(
      menu, goog.ui.Component.EventType.HIDE,
      function(/** goog.events.Event */ event) {
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
      },
      true, this);
  return true;
};

/** @type {goog.i18n.DateTimeFormat} */
cros.factory.Goofy.HMS_TIME_FORMAT = new goog.i18n.DateTimeFormat('HH:mm:ss');

/**
 * Returns a "View logs" submenu for a given test path.
 * @param {string} path
 * @return {!goog.ui.SubMenu}
 */
cros.factory.Goofy.prototype.createViewLogMenu = function(path) {
  var subMenu = new goog.ui.SubMenu('View logs');
  var loadingItem = new goog.ui.MenuItem('Loading...');
  loadingItem.setEnabled(false);
  subMenu.addItem(loadingItem);

  this.sendRpc(
      'GetTestHistory', [path],
      function(/** Array<cros.factory.HistoryMetadata> */ history) {
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
        goog.array.forEach(history, function(entry) {
          var status = entry.status ? entry.status.toLowerCase() : 'started';
          var title = count-- + '. Run at ';

          if (entry.init_time) {
            // TODO(jsalz): Localize (but not that important since this
            // is not for operators)

            title += cros.factory.Goofy.HMS_TIME_FORMAT.format(
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

          var item = new goog.ui.MenuItem(goog.dom.createDom(
              'span', 'goofy-view-logs-status-' + status, title));
          goog.events.listen(
              item, goog.ui.Component.EventType.ACTION, function(event) {
                this.showHistoryEntry(entry.path, entry.invocation);
              }, false, this);

          subMenu.addItem(item);
        }, this);
      });

  return subMenu;
};

/**
 * Displays a dialog containing logs.
 * @param {string|!goog.html.SafeHtml} title
 * @param {string} data text to show in the dialog.
 */
cros.factory.Goofy.prototype.showLogDialog = function(title, data) {
  var dialog = new goog.ui.Dialog();
  this.registerDialog(dialog);
  dialog.setModal(false);

  var viewSize =
      goog.dom.getViewportSize(goog.dom.getWindow(document) || window);
  var maxWidth = viewSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
  var maxHeight = viewSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;

  var style = goog.html.SafeStyle.create(
      {'max-width': maxWidth.toString(), 'max-height': maxHeight.toString()});
  cros.factory.Goofy.setDialogContent(
      dialog, goog.html.SafeHtml.concat(
                  goog.html.SafeHtml.create(
                      'div', {class: 'goofy-log-data', style: style}, data),
                  goog.html.SafeHtml.create('div', {class: 'goofy-log-time'})));
  dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
  dialog.setVisible(true);
  cros.factory.Goofy.setDialogTitle(dialog, title);

  var logDataElement =
      goog.dom.getElementByClass('goofy-log-data', dialog.getContentElement());
  logDataElement.scrollTop = logDataElement.scrollHeight;

  var logTimeElement =
      goog.dom.getElementByClass('goofy-log-time', dialog.getContentElement());
  var timer = new goog.Timer(1000);
  goog.events.listen(timer, goog.Timer.TICK, function(event) {
    // Show time in the same format as in the logs
    var timeStr =
        new goog.date.DateTime().toUTCIsoString(true, true).replace(' ', 'T');
    goog.dom.safe.setInnerHtml(
        /** @type {!Element} */ (logTimeElement),
        goog.html.SafeHtml.concat(
            cros.factory.i18n.i18nLabel('System time: '),
            goog.html.SafeHtml.htmlEscape(timeStr)));
  });
  timer.dispatchTick();
  timer.start();
  goog.events.listen(dialog, goog.ui.Component.EventType.HIDE, function(event) {
    timer.dispose();
  });
};


/**
 * Displays a dialog containing the contents of /var/log/messages.
 */
cros.factory.Goofy.prototype.viewVarLogMessages = function() {
  this.sendRpc('GetVarLogMessages', [], function(/** string */ data) {
    this.showLogDialog('/var/log/messages', data);
  });
};

/**
 * Displays a dialog containing the contents of /var/log/messages
 * before the last reboot.
 */
cros.factory.Goofy.prototype.viewVarLogMessagesBeforeReboot = function() {
  this.sendRpc(
      'GetVarLogMessagesBeforeReboot', [], function(/** ?string */ data) {
        data = data || 'Unable to find log message indicating reboot.';
        this.showLogDialog(
            cros.factory.i18n.i18nLabel('/var/log/messages before last reboot'),
            data);
      });
};

/**
 * Displays a dialog containing the contents of dmesg.
 */
cros.factory.Goofy.prototype.viewDmesg = function() {
  this.sendRpc('GetDmesg', [], function(/** string */ data) {
    this.showLogDialog('dmesg', data);
  });
};

/**
 * Add a factory note.
 * @param {string} name
 * @param {string} note
 * @param {string} level
 * @return {boolean}
 */
cros.factory.Goofy.prototype.addNote = function(name, note, level) {
  if (!name || !note) {
    alert('Both fields must not be empty!');
    return false;
  }
  // The timestamp for Note is set in the RPC call AddNote.
  this.sendRpc(
      'AddNote', [new cros.factory.Note(name, note, 0, level)],
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

  var viewSize =
      goog.dom.getViewportSize(goog.dom.getWindow(document) || window);
  var maxWidth = viewSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
  var maxHeight = viewSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;

  var style = goog.html.SafeStyle.create(
      {'max-width': maxWidth.toString(), 'max-height': maxHeight.toString()});

  var widthStyle =
      goog.html.SafeStyle.create({'max-width': maxWidth.toString()});

  var rows = [];
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('Your Name')),
    goog.html.SafeHtml.create(
        'td', {},
        goog.html.SafeHtml.create(
            'input', {id: 'goofy-addnote-name', style: widthStyle}))
  ]));
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('Note Content')),
    goog.html.SafeHtml.create(
        'td', {}, goog.html.SafeHtml.create(
                      'textarea', {id: 'goofy-addnote-text', style: style}))
  ]));

  var options = [];
  goog.array.forEach(cros.factory.NOTE_LEVEL, function(lvl) {
    var selected = lvl.name == 'INFO' ? 'selected' : null;
    options.push(goog.html.SafeHtml.create(
        'option', {value: lvl.name, selected: selected},
        lvl.name + ': ' + lvl.message));
  });
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('Severity')),
    goog.html.SafeHtml.create(
        'td', {}, goog.html.SafeHtml.create(
                      'select', {id: 'goofy-addnote-level'}, options))
  ]));

  var table =
      goog.html.SafeHtml.create('table', {class: 'goofy-addnote-table'}, rows);
  cros.factory.Goofy.setDialogContent(dialog, table);
  var buttons = goog.ui.Dialog.ButtonSet.createOkCancel();
  dialog.setButtonSet(buttons);
  dialog.setVisible(true);
  cros.factory.Goofy.setDialogTitle(
      dialog, cros.factory.i18n.i18nLabel('Add Note'));

  var nameBox = /** @type {HTMLInputElement} */ (
      document.getElementById('goofy-addnote-name'));
  var textBox = /** @type {HTMLTextAreaElement} */ (
      document.getElementById('goofy-addnote-text'));
  var levelBox = /** @type {HTMLSelectElement} */ (
      document.getElementById('goofy-addnote-level'));

  goog.events.listen(
      dialog, goog.ui.Dialog.EventType.SELECT,
      function(/** goog.ui.Dialog.Event */ event) {
        if (event.key == goog.ui.Dialog.DefaultButtonKeys.OK) {
          return this.addNote(nameBox.value, textBox.value, levelBox.value);
        }
      },
      false, this);
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
  cros.factory.Goofy.setDialogTitle(
      dialog, cros.factory.i18n.i18nLabel('Uploading factory logs...'));
  cros.factory.Goofy.setDialogContent(
      dialog,
      cros.factory.i18n.i18nLabel('Uploading factory logs.  Please wait...'));

  dialog.setButtonSet(null);
  dialog.setVisible(true);

  this.sendRpc(
      'UploadFactoryLogs', [name, serial, description],
      function(/** {name: string, size: number, key: string} */ info) {
        var {name: filename, size, key} = info;

        cros.factory.Goofy.setDialogContent(
            dialog,
            goog.html.SafeHtml.concat(
                goog.html.SafeHtml.htmlEscapePreservingNewlines(
                    'Success! Uploaded factory logs (' + size + ' bytes).\n' +
                    'The archive key is '),
                goog.html.SafeHtml.create(
                    'span', {class: 'goofy-ul-archive-key'}, key),
                goog.html.SafeHtml.htmlEscapePreservingNewlines(
                    '.\nPlease use this key when filing bugs\n' +
                    'or corresponding with the factory team.')));
        dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
        dialog.reposition();

        onSuccess();
      },
      function(/** {error: {message: string}} */ response) {
        cros.factory.Goofy.setDialogContent(
            dialog,
            'Unable to upload factory logs:\n' + response.error.message);
        dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
        dialog.reposition();
      });
};

/**
 * Pings the shopfloor server, displayed an alert if it cannot be reached.
 * @param {function()} onSuccess function to execute on success
 */
cros.factory.Goofy.prototype.pingShopFloorServer = function(onSuccess) {
  this.sendRpc(
      'PingShopFloorServer', [], onSuccess,
      function(/** {error: {message: string}} */ response) {
        this.alert(
            'Unable to contact shopfloor server.\n' + response.error.message);
      });
};

/**
 * Displays a dialog to upload factory logs to shopfloor server.
 */
cros.factory.Goofy.prototype.showUploadFactoryLogsDialog = function() {
  var dialog = new goog.ui.Dialog();
  this.registerDialog(dialog);
  dialog.setModal(true);

  var rows = [];
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('Your Name')),
    goog.html.SafeHtml.create(
        'td', {},
        goog.html.SafeHtml.create('input', {id: 'goofy-ul-name', size: 30}))
  ]));
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('Serial Number')),
    goog.html.SafeHtml.create('td', {}, goog.html.SafeHtml.create('input', {
      id: 'goofy-ul-serial',
      size: 30,
      value: this.systemInfo['serial_number'] ||
          this.systemInfo['mlb_serial_number'] || ''
    }))
  ]));
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('Bug Description')),
    goog.html.SafeHtml.create(
        'td', {}, goog.html.SafeHtml.create(
                      'input', {id: 'goofy-ul-description', size: 50}))
  ]));

  var table =
      goog.html.SafeHtml.create('table', {class: 'goofy-ul-table'}, rows);
  cros.factory.Goofy.setDialogContent(dialog, table);

  var buttons = goog.ui.Dialog.ButtonSet.createOkCancel();
  dialog.setButtonSet(buttons);

  cros.factory.Goofy.setDialogTitle(
      dialog, cros.factory.i18n.i18nLabel('Upload Factory Logs'));
  dialog.setVisible(true);

  var nameElt = /** @type {HTMLInputElement} */ (
      document.getElementById('goofy-ul-name'));
  var serialElt = /** @type {HTMLInputElement} */ (
      document.getElementById('goofy-ul-serial'));
  var descriptionElt = /** @type {HTMLInputElement} */ (
      document.getElementById('goofy-ul-description'));

  // Enable OK only if all three of these text fields are filled in.
  var /** Array<HTMLInputElement> */ elts =
      [nameElt, serialElt, descriptionElt];
  function checkOKEnablement() {
    buttons.setButtonEnabled(goog.ui.Dialog.DefaultButtonKeys.OK, true);
    goog.array.forEach(elts, function(elt) {
      if (goog.string.isEmpty(elt.value)) {
        buttons.setButtonEnabled(goog.ui.Dialog.DefaultButtonKeys.OK, false);
      }
    });
  }
  goog.array.forEach(elts, function(elt) {
    goog.events.listen(
        elt, [goog.events.EventType.CHANGE, goog.events.EventType.KEYUP],
        checkOKEnablement, false);
  });
  checkOKEnablement();

  goog.events.listen(
      dialog, goog.ui.Dialog.EventType.SELECT,
      function(/** goog.ui.Dialog.Event */ event) {
        if (event.key != goog.ui.Dialog.DefaultButtonKeys.OK)
          return;

        this.uploadFactoryLogs(
            nameElt.value, serialElt.value, descriptionElt.value,
            function() { dialog.dispose(); });

        event.preventDefault();
      },
      false, this);
};

/**
 * Saves factory logs to a USB drive.
 */
cros.factory.Goofy.prototype.saveFactoryLogsToUSB = function() {
  var title = cros.factory.i18n.i18nLabel('Save Factory Logs to USB');

  /** @this {cros.factory.Goofy} */
  function doSave() {
    /**
     * @this {cros.factory.Goofy}
     * @param {?string} id
     */
    function callback(id) {
      if (id == null) {
        // Cancelled.
        return;
      }

      var dialog = new goog.ui.Dialog();
      this.registerDialog(dialog);
      cros.factory.Goofy.setDialogTitle(dialog, title);
      cros.factory.Goofy.setDialogContent(
          dialog,
          cros.factory.i18n.i18nLabel('Saving factory logs to USB drive...'));
      dialog.setButtonSet(null);
      dialog.setVisible(true);
      this.positionOverConsole(dialog.getElement());
      this.sendRpc(
          'SaveLogsToUSB', [id],
          function(
              /**
               * {dev: string, name: string, size: number, temporary: boolean}
               */ info) {
            var {dev, name: filename, size, temporary} = info;

            if (temporary) {
              cros.factory.Goofy.setDialogContent(
                  dialog,
                  cros.factory.i18n.i18nLabel(
                      'Success! Saved factory logs ({size}) bytes) to {dev} ' +
                          'as\n{filename}. The drive has been unmounted.',
                      {size: size.toString(), dev: dev, filename: filename}));
            } else {
              cros.factory.Goofy.setDialogContent(
                  dialog,
                  cros.factory.i18n.i18nLabel(
                      'Success! Saved factory logs ({size}) bytes) to {dev} ' +
                          'as\n{filename}.',
                      {size: size.toString(), dev: dev, filename: filename}));
            }
            dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
            this.positionOverConsole(dialog.getElement());
          },
          function(/** {error: {message: string}} */ response) {
            cros.factory.Goofy.setDialogContent(
                dialog, 'Unable to save logs: ' + response.error.message);
            dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
            this.positionOverConsole(dialog.getElement());
          });
    }

    var idDialog = new goog.ui.Prompt('', '', goog.bind(callback, this));
    cros.factory.Goofy.setDialogTitle(idDialog, title);
    goog.dom.insertChildAt(
        idDialog.getContentElement(),
        cros.factory.i18n.i18nLabelNode(
            'Enter an optional identifier for the archive ' +
            '(or press Enter for none):'),
        0);
    this.registerDialog(idDialog);
    idDialog.setVisible(true);
    goog.dom.classlist.add(
        idDialog.getElement(), 'goofy-log-identifier-prompt');
    this.positionOverConsole(idDialog.getElement());
  }

  // Active timer, if any.
  var timer = null;

  var waitForUSBDialog = new goog.ui.Dialog();
  this.registerDialog(waitForUSBDialog);
  cros.factory.Goofy.setDialogContent(
      waitForUSBDialog, cros.factory.i18n.i18nLabel(
                            'Please insert a formatted USB stick' +
                            ' and wait a moment for it to be mounted.'));
  waitForUSBDialog.setButtonSet(new goog.ui.Dialog.ButtonSet().addButton(
      goog.ui.Dialog.ButtonSet.DefaultButtons.CANCEL, false, true));
  cros.factory.Goofy.setDialogTitle(waitForUSBDialog, title);

  /** @this {cros.factory.Goofy} */
  function waitForUSB() {
    /** @this {cros.factory.Goofy} */
    function restartWaitForUSB() {
      waitForUSBDialog.setVisible(true);
      this.positionOverConsole(waitForUSBDialog.getElement());
      timer = goog.Timer.callOnce(
          goog.bind(waitForUSB, this), cros.factory.MOUNT_USB_DELAY_MSEC);
    }
    this.sendRpc('IsUSBDriveAvailable', [], function(/** boolean */ available) {
      if (available) {
        waitForUSBDialog.dispose();
        doSave.call(this);
      } else {
        restartWaitForUSB.call(this);
      }
    }, goog.bind(restartWaitForUSB, this));
  }
  goog.events.listen(
      waitForUSBDialog, goog.ui.Component.EventType.HIDE, function(event) {
        if (timer) {
          goog.Timer.clear(timer);
        }
      });
  waitForUSB.call(this);
};

/** @type {goog.i18n.DateTimeFormat} */
cros.factory.Goofy.FULL_TIME_FORMAT =
    new goog.i18n.DateTimeFormat('yyyy-MM-dd HH:mm:ss.SSS');

/**
 * Displays a dialog containing history for a given test invocation.
 * @param {string} path
 * @param {string} invocation
 */
cros.factory.Goofy.prototype.showHistoryEntry = function(path, invocation) {
  this.sendRpc(
      'GetTestHistoryEntry', [path, invocation],
      function(/** cros.factory.HistoryEntry */ entry) {
        var viewSize =
            goog.dom.getViewportSize(goog.dom.getWindow(document) || window);
        var maxWidth = viewSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
        var maxHeight = viewSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;

        var metadataRows = [];
        goog.array.forEach(
            /** @type Array<Array<string>> */ ([
              ['status', 'Status'], ['init_time', 'Creation time'],
              ['start_time', 'Start time'], ['end_time', 'End time']
            ]),
            function(f) {
              var name = f[0];
              var title = f[1];

              if (entry.metadata[name]) {
                var /** string|number */ value = entry.metadata[name];
                delete entry.metadata[name];
                if (goog.string.endsWith(name, '_time')) {
                  value = cros.factory.Goofy.FULL_TIME_FORMAT.format(
                      new Date(value * 1000));
                }
                metadataRows.push(goog.html.SafeHtml.create('tr', {}, [
                  goog.html.SafeHtml.create('th', {}, title),
                  goog.html.SafeHtml.create('td', {}, value)
                ]));
              }
            },
            this);

        var keys = goog.object.getKeys(entry.metadata);
        keys.sort();
        goog.array.forEach(keys, function(key) {
          if (key == 'log_tail') {
            // Skip log_tail, since we already have the
            // entire log.
            return;
          }
          var /** string|number|Object */ value = entry.metadata[key];
          if (goog.isObject(value)) {
            value = goog.json.serialize(value);
          }
          metadataRows.push(goog.html.SafeHtml.create('tr', {}, [
            goog.html.SafeHtml.create('th', {}, key),
            goog.html.SafeHtml.create('td', {}, value)
          ]));
        });

        var metadataTable = goog.html.SafeHtml.create(
            'table', {class: 'goofy-history-metadata'}, metadataRows);

        var dialog = new goog.ui.Dialog();
        this.registerDialog(dialog);
        dialog.setTitle(
            entry.metadata.path + ' (invocation ' + entry.metadata.invocation +
            ')');
        dialog.setModal(false);
        var style = goog.html.SafeStyle.create(
            {'max-width': maxWidth, 'max-height': maxHeight});
        cros.factory.Goofy.setDialogContent(
            dialog,
            goog.html.SafeHtml.concat(
                goog.html.SafeHtml.create(
                    'div', {class: 'goofy-history', style: style}),
                goog.html.SafeHtml.create(
                    'div', {class: 'goofy-history-header'}, 'Test Info'),
                metadataTable,
                goog.html.SafeHtml.create(
                    'div', {class: 'goofy-history-header'}, 'Log'),
                goog.html.SafeHtml.create(
                    'div', {class: 'goofy-history-log'}, entry.log)));
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
cros.factory.Goofy.prototype.updateTestToolTip = function(
    path, tooltip, event) {
  var test = this.pathTestMap[path];

  tooltip.setText('');

  var errorMsg = test.state.error_msg;
  if ((test.state.status != 'FAILED' ||
       test.state.status != 'FAILED_AND_WAIVED') ||
      this.contextMenu || !errorMsg) {
    // Just show the test path, with a very short hover delay.
    tooltip.setText(test.path);
    tooltip.setHideDelayMs(cros.factory.NON_FAILING_TEST_HOVER_DELAY_MSEC);
  } else {
    // Show the last failure.
    var lines = errorMsg.split('\n');
    var html = [];
    html.push(
        goog.html.SafeHtml.htmlEscape(test.path + ' failed:'),
        goog.html.SafeHtml.create(
            'div', {class: 'goofy-test-failure'}, lines.shift()));

    if (lines.length) {
      html.push(
          goog.html.SafeHtml.create(
              'div', {class: 'goofy-test-failure-detail-link'},
              'Show more detail...'),
          goog.html.SafeHtml.create(
              'div', {class: 'goofy-test-failure-detail'},
              goog.html.SafeHtml.htmlEscapePreservingNewlines(
                  lines.join('\n'))));
    }
    if (test.state.invocation) {
      html.push(goog.html.SafeHtml.create(
          'div', {class: 'goofy-test-failure-view-log-link'}, 'View log...'));
    }

    tooltip.setSafeHtml(goog.html.SafeHtml.concat(html));

    if (lines.length) {
      var link = goog.dom.getElementByClass(
          'goofy-test-failure-detail-link', tooltip.getElement());
      goog.events.listen(link, goog.events.EventType.CLICK, function(event) {
        goog.dom.classlist.add(
            tooltip.getElement(), 'goofy-test-failure-expanded');
        tooltip.reposition();
      }, true);
    }
    if (test.state.invocation) {
      var link = goog.dom.getElementByClass(
          'goofy-test-failure-view-log-link', tooltip.getElement());
      goog.events.listen(link, goog.events.EventType.CLICK, function(event) {
        tooltip.dispose();
        this.showHistoryEntry(
            test.path, /** @type {string} */ (test.state.invocation));
      }, false, this);
    }
  }
};

/**
 * Sets up the UI for a the test list.  (Should be invoked only once, when
 * the test list is received.)
 * @param {cros.factory.TestListEntry} testList the test list (the return value
 *     of the GetTestList RPC call).
 */
cros.factory.Goofy.prototype.setTestList = function(testList) {
  cros.factory.logger.info(
      'Received test list: ' + goog.debug.expose(testList));
  goog.style.setElementShown(document.getElementById('goofy-loading'), false);

  this.addToNode(null, testList);
  // expandAll is necessary to get all the elements to actually be
  // created right away so we can add listeners.  We'll collapse it later.
  this.testTree.expandAll();
  this.testTree.render(document.getElementById('goofy-test-tree'));

  var addListener = goog.bind(
      /**
       * @param {string} path
       * @param {Element} labelElement
       * @param {Element} rowElement
       */
      function(path, labelElement, rowElement) {
        var tooltip = new goog.ui.AdvancedTooltip(rowElement);
        tooltip.setHideDelayMs(1000);
        this.tooltips.push(tooltip);
        goog.events.listen(
            tooltip, goog.ui.Component.EventType.BEFORE_SHOW,
            function(/** goog.events.Event */ event) {
              this.updateTestToolTip(path, tooltip, event);
            },
            true, this);
        goog.events.listen(
            rowElement, goog.events.EventType.CONTEXTMENU,
            function(/** goog.events.KeyEvent */ event) {
              if (event.ctrlKey) {
                // Ignore; let the default (browser) context menu
                // show up.
                return;
              }

              this.showTestPopup(path, labelElement);
              event.stopPropagation();
              event.preventDefault();
            },
            true, this);
        goog.events.listen(
            labelElement, goog.events.EventType.MOUSEDOWN,
            function(/** goog.events.KeyEvent */ event) {
              if (event.button == 0) {
                this.showTestPopup(path, labelElement);
                event.stopPropagation();
                event.preventDefault();
              }
            },
            true, this);
      },
      this);

  for (var path in this.pathNodeMap) {
    var node = this.pathNodeMap[path];
    addListener(path, node.getLabelElement(), node.getRowElement());
  }

  goog.array.forEach(
      [goog.events.EventType.MOUSEDOWN, goog.events.EventType.CONTEXTMENU],
      function(/** goog.events.EventType */ eventType) {
        goog.events.listen(
            document.getElementById('goofy-title'),
            eventType, function(/** goog.events.KeyEvent */ event) {
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
                  /**
                   * @param {cros.factory.i18n.TranslationDict} label
                   * @param {function(this:cros.factory.Goofy)} action
                   */
                  function(label, action) {
                    var item = new goog.ui.MenuItem(
                        cros.factory.i18n.i18nLabelNode(label));
                    goog.events.listen(
                        item, goog.ui.Component.EventType.ACTION, action, false,
                        this);
                    extraItems.push(item);
                  },
                  this);
              var _ = cros.factory.i18n.translation;

              if (this.engineeringMode) {
                addExtraItem(_('Update factory software'), this.updateFactory);
                extraItems.push(this.makeSwitchTestListMenu());
                extraItems.push(new goog.ui.MenuSeparator());
                addExtraItem(_('Save note on device'), this.showNoteDialog);
                addExtraItem(_('View notes'), this.viewNotes);
                extraItems.push(new goog.ui.MenuSeparator());
                addExtraItem(
                    _('View /var/log/messages'), this.viewVarLogMessages);
                addExtraItem(
                    _('View /var/log/messages before last reboot'),
                    this.viewVarLogMessagesBeforeReboot);
                addExtraItem(_('View dmesg'), this.viewDmesg);
                addExtraItem(
                    _('Device manager'),
                    goog.bind(
                        this.deviceManager.showWindow, this.deviceManager));
                if (cros.factory.ENABLE_DIAGNOSIS_TOOL) {
                  addExtraItem(
                      _('Diagnosis Tool'),
                      goog.bind(
                          this.diagnosisTool.showWindow, this.diagnosisTool));
                }
              }

              addExtraItem(
                  _('Save factory logs to USB drive...'),
                  this.saveFactoryLogsToUSB);
              addExtraItem(_('Upload factory logs...'), function() {
                this.pingShopFloorServer(this.showUploadFactoryLogsDialog);
              });
              addExtraItem(
                  _('Toggle engineering mode'), this.promptEngineeringPassword);

              this.showTestPopup(
                  '', document.getElementById('goofy-logo-text'), extraItems);

              event.stopPropagation();
              event.preventDefault();
            }, true, this);
      },
      this);

  this.testTree.collapseAll();
  this.sendRpc(
      'get_test_states', [],
      function(/** Object<string, cros.factory.TestState> */ stateMap) {
        for (var path in stateMap) {
          if (!goog.string.startsWith(path, '_')) {  // e.g., __jsonclass__
            this.setTestState(path, stateMap[path]);
          }
        }
      });
};

/**
 * Create the switch test list menu.
 * @return {!goog.ui.SubMenu}
 */
cros.factory.Goofy.prototype.makeSwitchTestListMenu = function() {
  var subMenu =
      new goog.ui.SubMenu(cros.factory.i18n.i18nLabelNode('Switch test list'));
  var _ = cros.factory.i18n.translation;
  goog.object.forEach(this.testLists, function(testList) {
    var item =
        new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(testList.name));
    item.setSelectable(true);
    item.setSelected(testList.enabled);
    subMenu.addItem(item);
    if (testList.enabled) {
      // Don't do anything if the active one is selected.
      return;
    }
    goog.events.listen(item, goog.ui.Component.EventType.ACTION, function() {
      var dialog = new goog.ui.Dialog();
      this.registerDialog(dialog);
      var title = cros.factory.i18n.stringFormat(
          _('Switch Test List: {test_list}'), {test_list: testList.name});
      cros.factory.Goofy.setDialogTitle(
          dialog, cros.factory.i18n.i18nLabel(title));
      cros.factory.Goofy.setDialogContent(
          dialog, cros.factory.i18n.i18nLabel(
                      'Warning: Switching to test list "{test_list}"' +
                          ' will clear all test state.\n' +
                          'Are you sure you want to proceed?',
                      {test_list: testList.name}));

      var buttonSet = new goog.ui.Dialog.ButtonSet();
      buttonSet.set(
          goog.ui.Dialog.DefaultButtonKeys.OK,
          cros.factory.i18n.i18nLabelNode('Yes, clear state and restart'));
      buttonSet.set(
          goog.ui.Dialog.DefaultButtonKeys.CANCEL,
          cros.factory.i18n.i18nLabelNode('Cancel'), true, true);
      dialog.setButtonSet(buttonSet);
      dialog.setVisible(true);

      dialog.reposition();

      goog.events.listen(
          dialog, goog.ui.Dialog.EventType.SELECT,
          function(/** goog.ui.Dialog.Event */ e) {
            if (e.key == goog.ui.Dialog.DefaultButtonKeys.OK) {
              var dialog = this.showIndefiniteActionDialog(
                  title, _('Switching test list. Please wait...'));
              this.sendRpc(
                  'SwitchTestList', [testList.id],
                  null,  // No action on success; wait to die.
                  function(/** {error: {message: string}} */ response) {
                    dialog.dispose();
                    this.alert(
                        'Unable to switch test list:\n' +
                        response.error.message);
                  });
            }
          },
          false, this);
    }, false, this);
  }, this);
  return subMenu;
};

/**
 * Displays a dialog for an operation that should never return.
 * @param {string|cros.factory.i18n.TranslationDict} title
 * @param {string|cros.factory.i18n.TranslationDict} label
 * @return {!goog.ui.Dialog}
 */
cros.factory.Goofy.prototype.showIndefiniteActionDialog = function(
    title, label) {
  var dialog = new goog.ui.Dialog();
  this.registerDialog(dialog);
  dialog.setHasTitleCloseButton(false);
  cros.factory.Goofy.setDialogTitle(dialog, cros.factory.i18n.i18nLabel(title));
  cros.factory.Goofy.setDialogContent(
      dialog, cros.factory.i18n.i18nLabel(label));
  dialog.setButtonSet(null);
  dialog.setVisible(true);
  dialog.reposition();
  return dialog;
};

/**
 * Sends an event to update factory software.
 * @export
 */
cros.factory.Goofy.prototype.updateFactory = function() {
  var _ = cros.factory.i18n.translation;
  var dialog = this.showIndefiniteActionDialog(
      _('Software update'), _('Updating factory software. Please wait...'));

  this.sendRpc(
      'UpdateFactory', [],
      function(
          /**
           * {success: boolean, updated: boolean, restart_time: ?number,
           *     error_msg: ?string}
           */ ret) {
        var {success, updated, restart_time: restartTime, error_msg: errorMsg} =
            ret;

        if (updated) {
          dialog.setTitle('Update succeeded');
          cros.factory.Goofy.setDialogContent(
              dialog,
              cros.factory.i18n.i18nLabel('Update succeeded. Restarting.'));
        } else if (success) {  // but not updated
          cros.factory.Goofy.setDialogContent(
              dialog,
              cros.factory.i18n.i18nLabel('No update is currently necessary.'));
          dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
        } else {
          cros.factory.Goofy.setDialogContent(
              dialog,
              goog.html.SafeHtml.concat(
                  cros.factory.i18n.i18nLabel('Update failed:'),
                  goog.html.SafeHtml.create('pre', {}, errorMsg || '')));
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
    goog.log.warning(
        cros.factory.logger, 'No node found for test path ' + path);
    return;
  }

  var elt = this.pathNodeMap[path].getElement();
  var test = this.pathTestMap[path];
  test.state = state;

  // Assign the appropriate class to the node, and remove all other
  // status classes.
  goog.dom.classlist.removeAll(
      elt, goog.array.filter(
               goog.dom.classlist.get(elt), function(/** string */ cls) {
                 return goog.string.startsWith(cls, 'goofy-status-');
               }));
  goog.dom.classlist.add(
      elt, 'goofy-status-' + state.status.toLowerCase().replace(/_/g, '-'));

  goog.dom.classlist.enable(elt, 'goofy-skip', state.skip);

  var visible = state.visible;
  goog.dom.classlist.enable(elt, 'goofy-test-visible', visible);
  goog.object.forEach(this.invocations, function(invoc, uuid) {
    if (invoc && invoc.path == path) {
      goog.dom.classlist.enable(invoc.iframe, 'goofy-test-visible', visible);
      if (visible) {
        invoc.iframe.contentWindow.focus();
      }
    }
  });

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
 * @param {goog.ui.tree.BaseNode} parent
 * @param {cros.factory.TestListEntry} test
 */
cros.factory.Goofy.prototype.addToNode = function(parent, test) {
  var node;
  if (parent == null) {
    node = this.testTree;
  } else {
    var html = cros.factory.i18n.i18nLabel(test.label);
    if (test.kbd_shortcut) {
      html = goog.html.SafeHtml.concat(
          goog.html.SafeHtml.create(
              'span', {class: 'goofy-kbd-shortcut'},
              'Alt-' + test.kbd_shortcut.toUpperCase()),
          html);
    }
    node = this.testTree.createNode();
    node.setSafeHtml(html);
    parent.addChild(node);
  }
  goog.array.forEach(
      test.subtests, function(/** cros.factory.TestListEntry */ subtest) {
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
  goog.log.info(cros.factory.logger, 'Sending event: ' + serialized);
  if (this.ws.isOpen()) {
    this.ws.send(serialized);
  }
};

/**
 * Calls an RPC function and invokes callback with the result.
 * @param {string} method
 * @param {Object} args
 * @param {?function(this:cros.factory.Goofy, ?)=} callback
 * @param {?function(this:cros.factory.Goofy, ?)=} opt_errorCallback
 */
cros.factory.Goofy.prototype.sendRpc = function(
    method, args, callback, opt_errorCallback) {
  var request = goog.json.serialize({method: method, params: args, id: 1});
  goog.log.info(cros.factory.logger, 'RPC request: ' + request);
  var factoryThis = this;
  goog.net.XhrIo.send('/goofy', function() {
    cros.factory.logger.info(
        'RPC response for ' + method + ': ' + this.getResponseText());

    if (this.getLastErrorCode() != goog.net.ErrorCode.NO_ERROR) {
      factoryThis.logToConsole(
          'RPC error calling ' + method + ': ' +
              goog.net.ErrorCode.getDebugMessage(this.getLastErrorCode()),
          'goofy-internal-error');
      // TODO(jsalz): handle error
      return;
    }

    var response =
        /** @type {{error: Object, result: Object}} */ (
            goog.json.unsafeParse(this.getResponseText()));
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
  }, 'POST', request);
};

/**
 * Sends a keepalive event if the web socket is open.
 */
cros.factory.Goofy.prototype.keepAlive = function() {
  if (this.ws.isOpen()) {
    this.sendEvent('goofy:keepalive', {uuid: this.uuid});
  }
};

/** @type {goog.i18n.NumberFormat} */
cros.factory.Goofy.LOAD_AVERAGE_FORMAT = new goog.i18n.NumberFormat('0.00');

/** @type {goog.i18n.NumberFormat} */
cros.factory.Goofy.PERCENT_CPU_FORMAT = new goog.i18n.NumberFormat('0.0%');

/** @type {goog.i18n.NumberFormat} */
cros.factory.Goofy.PERCENT_BATTERY_FORMAT = new goog.i18n.NumberFormat('0%');

/**
 * Gets the system status.
 */
cros.factory.Goofy.prototype.updateStatus = function() {
  this.sendRpc(
      'GetSystemStatus', [],
      function(/** cros.factory.SystemStatus */ systemStatus) {
        var status = systemStatus || {};
        this.systemInfo['ips'] = status['ips'];
        this.setSystemInfo(this.systemInfo);

        function setValue(/** string */ id, /** ?string */ value) {
          var element = document.getElementById(id);
          goog.dom.classlist.enable(
              element, 'goofy-value-known', value != null);
          goog.dom.setTextContent(
              goog.dom.getElementByClass('goofy-value', element), value || '');
        }

        /**
         * @param {?cros.factory.SystemStatus} oldStatus
         * @param {?cros.factory.SystemStatus} newStatus
         * @return {boolean}
         */
        function canCalculateCpuStatus(oldStatus, newStatus) {
          return !!oldStatus && !!oldStatus['cpu'] && !!newStatus['cpu'];
        }

        setValue(
            'goofy-load-average', status['load_avg'] ?
                cros.factory.Goofy.LOAD_AVERAGE_FORMAT.format(
                    status['load_avg'][0]) :
                null);

        if (canCalculateCpuStatus(this.lastStatus, status)) {
          var lastCpu = goog.math.sum.apply(this, this.lastStatus['cpu']);
          var currentCpu = goog.math.sum.apply(this, status['cpu']);
          var /** number */ lastIdle = this.lastStatus['cpu'][3];
          var /** number */ currentIdle = status['cpu'][3];
          var deltaIdle = currentIdle - lastIdle;
          var deltaTotal = currentCpu - lastCpu;
          setValue(
              'goofy-percent-cpu', cros.factory.Goofy.PERCENT_CPU_FORMAT.format(
                                       (deltaTotal - deltaIdle) / deltaTotal));
        } else {
          setValue('goofy-percent-cpu', null);
        }

        var chargeIndicator =
            document.getElementById('goofy-battery-charge-indicator');
        var percent = null;
        var batteryChargeState = 'unknown';
        if (status.battery) {
          if (status.battery.charge_fraction != null) {
            percent = cros.factory.Goofy.PERCENT_BATTERY_FORMAT.format(
                status.battery.charge_fraction);
          }
          if (goog.array.contains(
                  ['Full', 'Charging', 'Discharging'],
                  status.battery.charge_state)) {
            batteryChargeState = status.battery.charge_state.toLowerCase();
          }
        }
        setValue('goofy-percent-battery', percent);
        goog.dom.classlist.set(
            chargeIndicator, 'goofy-battery-' + batteryChargeState);

        var /** ?number */ temperature = status['temperature'];
        var temp = null;
        if (temperature != null) {
          temp = Math.round(temperature) + '°C';
        }
        setValue('goofy-temperature', temp);

        var eth_indicator = document.getElementById('goofy-eth-indicator');
        goog.dom.classlist.enable(
            eth_indicator, 'goofy-eth-enabled', status['eth_on']);
        var wlan_indicator = document.getElementById('goofy-wlan-indicator');
        goog.dom.classlist.enable(
            wlan_indicator, 'goofy-wlan-enabled', status['wlan_on']);

        this.lastStatus = status;
      });
};

/**
 * Writes a message to the console log.
 * @param {string} message
 * @param {Object|Array<string>|string=} opt_attributes attributes to add
 *     to the div element containing the log entry.
 */
cros.factory.Goofy.prototype.logToConsole = function(message, opt_attributes) {
  var div = goog.dom.createDom('div', opt_attributes);
  goog.dom.classlist.add(div, 'goofy-log-line');
  div.appendChild(document.createTextNode(message));
  this.console.appendChild(div);

  // Restrict the size of the log to avoid UI lag.
  if (this.console.childNodes.length > cros.factory.MAX_LINE_CONSOLE_LOG) {
    this.console.removeChild(this.console.firstChild);
  }

  // Scroll to bottom.  TODO(jsalz): Scroll only if already at the bottom,
  // or add scroll lock.
  var scrollPane = goog.dom.getAncestorByClass(
      this.console, 'goog-splitpane-second-container');
  scrollPane.scrollTop = scrollPane.scrollHeight;
};

/**
 * Logs an "internal" message to the console (as opposed to a line from
 * console.log).
 * @param {string} message
 */
cros.factory.Goofy.prototype.logInternal = function(message) {
  this.logToConsole(message, 'goofy-internal-log');
};

/**
 * Hides tooltips, and cancels pending shows.
 * @suppress {accessControls}
 */
cros.factory.Goofy.prototype.hideTooltips = function() {
  goog.array.forEach(this.tooltips, function(tooltip) {
    tooltip.clearShowTimer();
    tooltip.setVisible(false);
  });
};

/**
 * @type {{runtime: {sendMessage: function(string, Object, function(Object))}}}
 */
window.chrome;

/**
 * Handles an event sends from the backend.
 * @suppress {missingProperties}
 * @param {string} jsonMessage the message as a JSON string.
 */
cros.factory.Goofy.prototype.handleBackendEvent = function(jsonMessage) {
  goog.log.info(cros.factory.logger, 'Got message: ' + jsonMessage);
  var untypedMessage =
      /** @type {{type: string}} */ (goog.json.unsafeParse(jsonMessage));
  var messageType = untypedMessage.type;

  if (messageType == 'goofy:hello') {
    const message = /** @type {{uuid: string}} */ (untypedMessage);
    if (this.uuid && message.uuid != this.uuid) {
      // The goofy process has changed; reload the page.
      goog.log.info(cros.factory.logger, 'Incorrect UUID; reloading');
      window.location.reload();
      return;
    } else {
      this.uuid = message.uuid;
      // Send a keepAlive to confirm the UUID with the backend.
      this.keepAlive();
      // TODO(jsalz): Process version number information.
    }
  } else if (messageType == 'goofy:log') {
    const message = /** @type {{message: string}} */ (untypedMessage);
    this.logToConsole(message.message);
  } else if (messageType == 'goofy:state_change') {
    const message =
        /** @type {{path: string, state: cros.factory.TestState}} */ (
            untypedMessage);
    this.setTestState(message.path, message.state);
  } else if (messageType == 'goofy:init_test_ui') {
    const message =
        /**
         * @type {{test: string, invocation: string, parent_invocation: string,
         *     html: string}}
         */ (untypedMessage);
    var invocation = this.getOrCreateInvocation(
        message.test, message.invocation, message.parent_invocation);
    if (invocation && invocation.iframe) {
      goog.dom.iframe.writeContent(invocation.iframe, message['html']);
      this.updateCSSClassesInDocument(invocation.iframe.contentDocument);
      // In the content window's evaluation context, add our keydown
      // listener.
      invocation.iframe.contentWindow.eval(
          'window.addEventListener("keydown", ' +
          'window.test.invocation.goofy.boundKeyListener)');
    }
  } else if (messageType == 'goofy:set_html') {
    const message =
        /**
         * @type {{test: string, invocation: string, parent_invocation: string,
         *     id: ?string, append: boolean, html: string}}
         */ (untypedMessage);
    var invocation = this.getOrCreateInvocation(
        message.test, message.invocation, message.parent_invocation);
    if (invocation && invocation.iframe) {
      if (message.id) {
        var element = /** @type {Element} */ (
            invocation.iframe.contentDocument.getElementById(message.id));
        if (element) {
          if (!message.append) {
            element.innerHTML = '';
          }
          element.innerHTML += message.html;
        }
      } else {
        var body = invocation.iframe.contentDocument.body;
        if (body) {
          if (!message.append) {
            body.innerHTML = '';
          }
          body.innerHTML += message.html;
        } else {
          this.logToConsole('Test UI not initialized.', 'goofy-internal-error');
        }
      }
    }
  } else if (messageType == 'goofy:run_js') {
    const message =
        /**
         * @type {{test: string, invocation: string, parent_invocation: string,
         *     args: Object, js: string}}
         */ (untypedMessage);
    var invocation = this.getOrCreateInvocation(
        message.test, message.invocation, message.parent_invocation);
    if (invocation && invocation.iframe) {
      // We need to evaluate the code in the context of the content
      // window, but we also need to give it a variable.  Stash it
      // in the window and load it directly in the eval command.
      invocation.iframe.contentWindow.__goofy_args = message.args;
      invocation.iframe.contentWindow.eval(
          'var args = window.__goofy_args;' + message.js);
      if (invocation && invocation.iframe) {
        delete invocation.iframe.contentWindow.__goofy_args;
      }
    }
  } else if (messageType == 'goofy:call_js_function') {
    const message =
        /**
         * @type {{test: string, invocation: string, parent_invocation: string,
         *     name: string, args: Object}}
         */ (untypedMessage);
    var invocation = this.getOrCreateInvocation(
        message.test, message.invocation, message.parent_invocation);
    if (invocation && invocation.iframe) {
      var func =
          /** @type {function(?)} */ (
              invocation.iframe.contentWindow.eval(message.name));
      if (func) {
        func.apply(invocation.iframe.contentWindow, message.args);
      } else {
        cros.factory.logger.severe(
            'Unable to find function ' + func + ' in UI for test ' +
            message.test);
      }
    }
  } else if (messageType == 'goofy:extension_rpc') {
    const message =
        /**
         * @type {{is_response: boolean, name: string, args: Object,
         *     rpc_id: string}}
         */ (untypedMessage);
    if (!message.is_response) {
      var goofy = this;  // Save namespace for response fallback.
      window.chrome.runtime.sendMessage(
          cros.factory.EXTENSION_ID, {name: message.name, args: message.args},
          function(result) {
            goofy.sendEvent(messageType, {
              name: message.name,
              rpc_id: message.rpc_id,
              is_response: true,
              args: result
            });
          });
    }
  } else if (messageType == 'goofy:destroy_test') {
    const message = /** @type {{invocation: string}} */ (untypedMessage);
    // We send destroy_test event only in the top-level invocation from
    // Goofy backend.
    cros.factory.logger.info(
        'Received destroy_test event for top-level invocation ' +
        message.invocation);
    var invocation = this.invocations[message.invocation];
    if (invocation) {
      invocation.dispose();
    }
  } else if (messageType == 'goofy:system_info') {
    const message =
        /** @type {{system_info: Object<string, string>}} */ (untypedMessage);
    this.setSystemInfo(message['system_info']);
  } else if (messageType == 'goofy:pending_shutdown') {
    const message =
        /** @type {cros.factory.PendingShutdownEvent} */ (untypedMessage);
    this.setPendingShutdown(message);
  } else if (messageType == 'goofy:update_notes') {
    this.sendRpc('get_shared_data', ['factory_note', true], this.updateNote);
  } else if (messageType == 'goofy:diagnosis_tool:event') {
    const message = /** @type {!Object} */ (untypedMessage);
    this.diagnosisTool.handleBackendEvent(message);
  } else if (messageType == 'goofy:hide_tooltips') {
    this.hideTooltips();
  }
};

/**
 * External reference used for terminal.
 */

/**
 * @constructor
 * @param {Object} setting
 */
var Terminal = function(setting) {};

/** @type {function(string, function(string))} */
Terminal.prototype.on;

/** @type {function(Element)} */
Terminal.prototype.open;

/** @type {function(string)} */
Terminal.prototype.write;

/** @type {function(number, number)} */
Terminal.prototype.resize;

/** @type {function(number, number)} */
Terminal.prototype.refresh;

/** @type {number} */
Terminal.prototype.cols;

/** @type {number} */
Terminal.prototype.rows;

/** @type {Element} */
Terminal.prototype.element;

var Base64 = {};

/** @type {function(string): string} */
Base64.encode = function() {};

/** @type {function(string): string} */
Base64.decode = function() {};

/** @type {function(Element): jQuery.Type} */
var jQuery = function() {};

/** @constructor */
jQuery.Type = function() {};

/** @type function(string): jQuery.Type */
jQuery.Type.prototype.find;

/** @type function(Object) */
jQuery.Type.prototype.draggable;

/** @type function(string, string=): string */
jQuery.Type.prototype.css;

/** @type function(): number */
jQuery.Type.prototype.width;

/** @type function(): number */
jQuery.Type.prototype.height;

/** @type function() */
jQuery.Type.prototype.resizable;

/** @type function(string, function()) */
jQuery.Type.prototype.bind;

/**
 * Start the terminal session.
 */
cros.factory.Goofy.prototype.launchTerminal = function() {
  this.sendEvent('goofy:key_filter_mode', {enabled: false});

  if (this.terminal_win) {
    goog.style.setElementShown(this.terminal_win, true);
    goog.style.setStyle(
        document.getElementById('goofy-terminal'), 'opacity', 1.0);
    return;
  }

  var mini = goog.dom.createDom('div', {class: 'goofy-terminal-minimize'});
  var close = goog.dom.createDom('div', {class: 'goofy-terminal-close'});
  var win = goog.dom.createDom(
      'div', {class: 'goofy-terminal-window', id: 'goofy-terminal-window'},
      goog.dom.createDom('div', {class: 'goofy-terminal-title'}, 'Terminal'),
      goog.dom.createDom(
          'div', {class: 'goofy-terminal-control'}, mini, close));

  goog.events.listen(
      close, goog.events.EventType.MOUSEUP, this.closeTerminal.bind(this));
  goog.events.listen(
      mini, goog.events.EventType.MOUSEUP, this.hideTerminal.bind(this));
  goog.dom.appendChild(document.body, win);

  var ws_url = 'ws://' + window.location.host + '/pty';
  var sock = new WebSocket(ws_url);

  this.terminal_sock = sock;
  this.terminal_win = win;

  sock.onerror = function(/** Error */ e) {
    goog.log.info(cros.factory.logger, 'socket error', e);
  };
  jQuery(win).draggable({cancel: '.terminal'});
  sock.onopen = function(e) {
    var term =
        new Terminal({cols: 80, rows: 24, useStyle: true, screenKeys: true});
    term.open(win);
    term.on('data', function(data) { sock.send(data); });
    sock.onmessage = function(/** {data: string} */ msg) {
      term.write(Base64.decode(msg.data));
    };

    var terminalWindow = document.getElementById('goofy-terminal-window');
    var /** jQuery.Type */ $terminalWindow = jQuery(terminalWindow);
    var /** jQuery.Type */ $terminal = $terminalWindow.find('.terminal');
    var termBorderRightWidth = $terminal.css('border-right-width');
    var termBorderBottomWidth = $terminal.css('border-bottom-width');
    var totalWidthOffset = $terminalWindow.width() - term.element.clientWidth;
    var totalHeightOffset =
        $terminalWindow.height() - term.element.clientHeight;

    // hide terminal right and bottom border
    $terminal.css('border-right-width', '0px');
    $terminal.css('border-bottom-width', '0px');

    // initial terminal-window size
    terminalWindow.style.width = term.element.clientWidth + totalWidthOffset;
    terminalWindow.style.height = term.element.clientHeight + totalHeightOffset;

    $terminalWindow.resizable();
    $terminalWindow.bind('resize', function() {
      // Ghost uses the CONTROL_START and CONTROL_END to know the control
      // string.
      // format: CONTROL_START ControlString CONTROL_END
      var CONTROL_START = 128;
      var CONTROL_END = 129;

      // If there is no terminal now, just return.
      // It may happen when we close the window
      if (term.element.clientWidth == 0 || term.element.clientHeight == 0) {
        return;
      }

      // convert to cols/rows
      var widthToColsFactor = term.cols / term.element.clientWidth;
      var heightToRowsFactor = term.rows / term.element.clientHeight;
      var newTermWidth =
          parseInt(terminalWindow.style.width, 10) - totalWidthOffset;
      var newTermHeight =
          parseInt(terminalWindow.style.height, 10) - totalHeightOffset;
      var newCols = Math.floor(newTermWidth * widthToColsFactor);
      var newRows = Math.floor(newTermHeight * heightToRowsFactor);
      if (newCols != term.cols || newRows != term.rows) {
        var msg = {command: 'resize', params: [newRows, newCols]};
        term.resize(newCols, newRows);
        term.refresh(0, term.rows - 1);

        // Fine tune terminal-window size to match terminal.
        // Prevent white space between terminal-window and terminal.
        terminalWindow.style.width =
            term.element.clientWidth + totalWidthOffset;
        terminalWindow.style.height =
            term.element.clientHeight + totalHeightOffset;

        // Send to ghost to set new size
        sock.send((new Uint8Array([CONTROL_START])).buffer);
        sock.send(JSON.stringify(msg));
        sock.send((new Uint8Array([CONTROL_END])).buffer);
      }
    });
  };
  sock.onclose = goog.bind(function() { this.closeTerminal(); }, this);
};

/**
 * Close the terminal window.
 */
cros.factory.Goofy.prototype.closeTerminal = function() {
  if (this.terminal_win) {
    goog.dom.removeNode(this.terminal_win);
    this.terminal_sock.close();
    this.terminal_win = null;
    this.terminal_sock = null;
    this.sendEvent('goofy:key_filter_mode', {enabled: true});
  }
};

/**
 * Hide the terminal window.
 */
cros.factory.Goofy.prototype.hideTerminal = function() {
  goog.style.setElementShown(this.terminal_win, false);
  goog.style.setStyle(
      document.getElementById('goofy-terminal'), 'opacity', 0.5);
  this.sendEvent('goofy:key_filter_mode', {enabled: true});
};

goog.events.listenOnce(window, goog.events.EventType.LOAD, function() {
  window.goofy = new cros.factory.Goofy();
  window.goofy.preInit();
});
