// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.Goofy');

goog.require('_');
goog.require('cros.factory.DeviceManager');
goog.require('cros.factory.DiagnosisTool');
goog.require('cros.factory.Plugin');
goog.require('cros.factory.i18n');
goog.require('cros.factory.testUI.Manager');
goog.require('cros.factory.testUI.TabManager');
goog.require('cros.factory.testUI.TileManager');
goog.require('cros.factory.utils');
goog.require('goog.crypt');
goog.require('goog.crypt.Sha1');
goog.require('goog.date.DateTime');
goog.require('goog.debug.FancyWindow');
goog.require('goog.debug.Logger');
goog.require('goog.dom');
goog.require('goog.dom.iframe');
goog.require('goog.dom.safe');
goog.require('goog.events');
goog.require('goog.events.EventType');
goog.require('goog.events.KeyCodes');
goog.require('goog.html.SafeHtml');
goog.require('goog.html.SafeStyle');
goog.require('goog.i18n.DateTimeFormat');
goog.require('goog.i18n.NumberFormat');  // Used by status_monitor.js
goog.require('goog.math');
goog.require('goog.net.WebSocket');
goog.require('goog.net.XhrIo');
goog.require('goog.positioning');
goog.require('goog.positioning.AnchoredViewportPosition');
goog.require('goog.positioning.Corner');
goog.require('goog.positioning.CornerBit');
goog.require('goog.positioning.Overflow');
goog.require('goog.string');
goog.require('goog.style');
goog.require('goog.ui.AdvancedTooltip');
goog.require('goog.ui.Component.EventType');
goog.require('goog.ui.Container');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');
goog.require('goog.ui.MenuSeparator');
goog.require('goog.ui.PopupMenu');
goog.require('goog.ui.ProgressBar');
goog.require('goog.ui.Prompt');
goog.require('goog.ui.SplitPane');
goog.require('goog.ui.SubMenu');
goog.require('goog.ui.ToggleButton');  // Indirectly used by default_test_ui.js
goog.require('goog.ui.decorate');  // Used by default_test_ui.js
goog.require('goog.ui.tree.TreeControl');

/**
 * @type {?goog.debug.Logger}
 * @const
 */
cros.factory.logger = goog.log.getLogger('cros.factory');

/**
 * Keep-alive interval for the WebSocket.  (Chrome times out WebSockets every
 * ~1 min, so 30 s seems like a good interval.)
 * @const
 * @type {number}
 */
cros.factory.KEEP_ALIVE_INTERVAL_MSEC = 30000;

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
 * @const
 * @type {number}
 */
cros.factory.CONTROL_PANEL_MIN_WIDTH = 320;

/**
 * Height of the log pane, as a fraction of the viewport size.
 * @const
 * @type {number}
 */
cros.factory.LOG_PANE_HEIGHT_FRACTION = 0.2;

/**
 * Minimum height of the log pane, in pixels.
 * @const
 * @type {number}
 */
cros.factory.LOG_PANE_MIN_HEIGHT = 170;

/**
 * Hover delay for a non-failing test.
 * @const
 * @type {number}
 */
cros.factory.NON_FAILING_TEST_HOVER_DELAY_MSEC = 250;

/**
 * Factory Test Extension ID to support calling chrome API via RPC.
 * @const
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
 * @const
 */
cros.factory.MAX_LINE_CONSOLE_LOG = 1024;

/**
 * An item in the test list.
 * closure-compiler typedef can't handle recursive typedef, so the subtests
 * type is unchecked.
 * TODO(pihsun): Rewrite this type so the subtests can have correct type.
 * @typedef {{path: string, label: !cros.factory.i18n.TranslationDict,
 *     disable_abort: boolean, subtests: !Array<!cros.factory.TestListEntry>,
 *     state: !cros.factory.TestState, args: Object, pytest_name: ?string}}
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
 * @typedef {{startTime: number, endTime: number, status: string,
 *     testName: string, testRunId: string}}
 */
cros.factory.HistoryMetadata;

/**
 * Entry in test history.
 * @typedef {{testlog: !cros.factory.HistoryMetadata, log: string,
 *     source_code: string}}
 */
cros.factory.HistoryEntry;

/**
 * TestState object in an event or RPC response.
 * @typedef {{status: string, skip: boolean, count: number,
 *     error_msg: string, invocation: ?string, iterations_left: number,
 *     retries_left: number, shutdown_count: number}}
 */
cros.factory.TestState;

/**
 * Information about a test list.
 * @typedef {{id: string, name: !cros.factory.i18n.TranslationDict,
 *     enabled: boolean}}
 */
cros.factory.TestListInfo;

/**
 * @typedef {{text: !cros.factory.i18n.TranslationDict, id: string,
 *     eng_mode_only: boolean}}
 */
cros.factory.PluginMenuItem;

/**
 * @typedef {{action: string, data: string}}
 */
cros.factory.PluginMenuReturnData;

/**
 * Config for goofy plugin frontend UI.
 * @typedef {{url: string, location: string}}
 */
cros.factory.PluginFrontendConfig;

/**
 * The i18n name of special keys.
 * @type {!Map<string, !cros.factory.i18n.TranslationDict>}
 */
const KEY_NAME_MAP = new Map([
  ['ENTER', _('Enter')],
  ['ESCAPE', _('ESC')],
  [' ', _('Space')]
]);

/**
 * Public API for tests.
 */
cros.factory.Test = class {
  /**
   * @param {!cros.factory.Invocation} invocation
   */
  constructor(invocation) {
    /**
     * The invocation of this test.
     * @type {!cros.factory.Invocation}
     */
    this.invocation = invocation;

    /**
     * Map of key values to handlers.
     * @type {!Map<string, {callback: function(?goog.events.KeyEvent),
     *                      button: ?Element}>}
     * @private
     */
    this.keyHandlers_ = new Map();

    /**
     * Whether the keydown listener is set on the contentWindow.
     * @type {boolean}
     */
    this.keyListenerSet_ = false;
  }

  /**
   * Passes the test.
   * @export
   */
  pass() {
    this.sendTestEvent('goofy_ui_task_end', {
      'status': 'PASSED'
    });
  }

  /**
   * Fails the test with the given error message.
   * @param {string} errorMsg
   * @export
   */
  fail(errorMsg) {
    this.sendTestEvent('goofy_ui_task_end', {
      'status': 'FAILED',
      'error_msg': errorMsg
    });
  }

  /**
   * Try to abort the test from UI by operator. If test parameter
   * 'disable_abort' is set and not in engineering mode, alert and
   * return.
   * @param {string=} errorMsg
   * @export
   */
  userAbort(errorMsg = 'Marked failed by operator') {
    const goofy = this.invocation.goofy;
    if (goofy.engineeringMode ||
        !goofy.pathTestMap[this.invocation.path].disable_abort) {
      this.fail(errorMsg);
    } else {
      goofy.alert('You can only abort this test in engineering mode.');
    }
  }

  /**
   * Sends an event to the test backend.
   * @param {string} subtype the event type
   * @param {?Object} data the event data
   * @export
   */
  sendTestEvent(subtype, data) {
    this.invocation.goofy.sendEvent('goofy:test_ui_event', {
      'test': this.invocation.path,
      'invocation': this.invocation.uuid,
      'subtype': subtype,
      'data': data
    });
  }

  /**
   * Binds a key to a handler.
   * @param {string} key the key to bind.
   * @param {function(?goog.events.KeyEvent)} callback the function to call when
   *     the key is pressed.
   * @param {boolean=} once whether the callback should only be triggered once.
   * @param {boolean=} virtual whether a virtual key button should be added.
   * @export
   */
  bindKey(key, callback, once = false, virtual = true) {
    key = key.toUpperCase();
    if (!this.keyListenerSet_) {
      // Set up the listener. We listen on KEYDOWN instead of KEYUP, so it won't
      // be accidentally triggered after a dialog is dismissed.
      goog.events.listen(
          this.invocation.iframe.contentWindow, goog.events.EventType.KEYDOWN,
          (/** !goog.events.KeyEvent */ event) => {
            const handler = this.keyHandlers_.get(event.key.toUpperCase());
            if (handler) {
              handler.callback(event);
            }
          });
      this.keyListenerSet_ = true;
    }
    const handler = {};
    if (once) {
      handler.callback = (event) => {
        callback(event);
        this.unbindKey(key);
      };
    } else {
      handler.callback = callback;
    }
    if (virtual) {
      const button = this.addVirtualKey_(key);
      if (button) {
        handler.button = button;
      }
    }
    this.keyHandlers_.set(key, handler);
  }

  /**
   * Unbinds a key and removes its handler.
   * @param {string} key the key to unbind.
   * @export
   */
  unbindKey(key) {
    key = key.toUpperCase();
    const handler = this.keyHandlers_.get(key);
    if (handler && handler.button) {
      handler.button.remove();
    }
    this.keyHandlers_.delete(key);
  }

  /**
   * Unbinds all keys.
   * @export
   */
  unbindAllKeys() {
    for (const {button} of this.keyHandlers_.values()) {
      if (button) {
        button.remove();
      }
    }
    // We don't actually remove the handler, just let it does nothing should be
    // good enough.
    this.keyHandlers_.clear();
  }

  /**
   * Binds standard pass keys (enter, space, 'P').
   * @export
   */
  bindStandardPassKeys() {
    this.bindKey('ENTER', () => { this.pass(); });
    for (const key of [' ', 'P']) {
      this.bindKey(key, () => { this.pass(); }, false, false);
    }
  }

  /**
   * Binds standard fail keys (ESC, 'F').
   * @export
   */
  bindStandardFailKeys() {
    this.bindKey('ESCAPE', () => { this.userAbort(); });
    this.bindKey('F', () => { this.userAbort(); }, false, false);
  }

  /**
   * Binds standard pass and fail keys.
   * @export
   */
  bindStandardKeys() {
    this.bindStandardPassKeys();
    this.bindStandardFailKeys();
  }

  /**
   * Triggers an update check.
   * @export
   */
  updateFactory() {
    this.invocation.goofy.updateFactory();
  }

  /**
   * Displays an alert.
   * @param {string|!cros.factory.i18n.TranslationDict|!goog.html.SafeHtml}
   *     message
   * @export
   */
  alert(message) {
    this.invocation.goofy.alert(message);
  }

  /**
   * Sets iframe to fullscreen size.
   * Also iframe gets higher z-index than test panel so it will cover all other
   * stuffs in goofy.
   * @param {boolean} enable fullscreen iframe or not.
   * @export
   */
  setFullScreen(enable) {
    this.invocation.iframe.classList.toggle('goofy-test-fullscreen', enable);
    if (enable) {
      this.invocation.goofy.hideTooltips();
    }
  }

  /**
   * Get the i18n name to be displayed for keyCode.
   * @param {string} key
   * @return {!cros.factory.i18n.TranslationDict}
   * @private
   */
  getKeyName_(key) {
    return KEY_NAME_MAP.get(key) || cros.factory.i18n.noTranslation(key);
  }

  /**
   * Add a virtualkey button, and return the button.
   * @param {string} key the key name which handler should be triggered when
   *     clicking the button.
   * @return {?Element}
   * @private
   */
  addVirtualKey_(key) {
    const template = this.invocation.iframe.contentWindow['template'];
    if (!template) {
      return null;
    }
    const label = this.getKeyName_(key);
    const button = template.addButton(label);
    goog.events.listen(button, goog.events.EventType.CLICK, () => {
      const handler = this.keyHandlers_.get(key);
      if (handler) {
        // Not a key event, passing null to callback.
        handler.callback(null);
      }
    });
    return button;
  }
};

/**
 * UI for a single test invocation.
 */
cros.factory.Invocation = class {
  /**
   * @param {!cros.factory.Goofy} goofy
   * @param {string} path
   * @param {string} uuid
   */
  constructor(goofy, path, uuid) {
    /**
     * Reference to the Goofy object.
     * @type {!cros.factory.Goofy}
     */
    this.goofy = goofy;

    /**
     * Full path of the test.
     * @type {string}
     */
    this.path = path;

    /**
     * UUID of the invocation.
     * @type {string}
     */
    this.uuid = uuid;

    /**
     * The iframe containing the test.
     * @type {!HTMLIFrameElement}
     */
    this.iframe = goog.asserts.assertInstanceof(
        document.createElement('iframe'), HTMLIFrameElement);
    this.iframe.src = '/default_test_ui.html';
    this.iframe.classList.add('goofy-test-iframe');

    this.goofy.addInvocationUI(this);

    /**
     * A promise that would be resolved after the test iframe is loaded.
     * @type {!Promise}
     */
    this.loaded = new Promise((resolve) => {
      this.iframe.onload = resolve;
    });

    /**
     * Test API for the invocation.
     * @type {!cros.factory.Test}
     */
    this.test = new cros.factory.Test(this);

    // Export the libraries to test iframe.
    this.iframe.contentWindow.cros = cros;
    this.iframe.contentWindow.goog = goog;
    this.iframe.contentWindow.test = this.test;
    this.iframe.contentWindow._ = _;
  }

  /**
   * Returns test list entry for this invocation.
   * @return {!cros.factory.TestListEntry}
   */
  getTestListEntry() {
    return this.goofy.pathTestMap[this.path];
  }

  /**
   * Dispose the invocation (and destroys the iframe).
   */
  dispose() {
    goog.log.info(cros.factory.logger, `Cleaning up invocation ${this.uuid}`);

    this.goofy.removeInvocationUI(this);
    this.iframe.remove();
    this.goofy.invocations.delete(this.uuid);

    goog.log.info(
        cros.factory.logger, `Top-level invocation ${this.uuid} disposed`);
  }
};

/**
 * Types of notes.
 * @type {!Array<{name: string, message: string}>}
 */
cros.factory.NOTE_LEVEL = [
  {name: 'INFO', message: 'Informative message only'},
  {name: 'WARNING', message: 'Displays a warning icon'},
  {name: 'CRITICAL', message: 'Testing is stopped indefinitely'}
];

/**
 * A factory note.
 */
cros.factory.Note = class {
  /**
   * @param {string} name
   * @param {string} text
   * @param {number} timestamp
   * @param {string} level
   */
  constructor(name, text, timestamp, level) {
    this.name = name;
    this.text = text;
    this.timestamp = timestamp;
    this.level = level;
  }
};

/**
 * UI for displaying critical factory notes.
 */
cros.factory.CriticalNoteDisplay = class {
  /**
   * @param {!cros.factory.Goofy} goofy
   */
  constructor(goofy) {
    this.goofy = goofy;
    this.div = goog.dom.createDom('div', 'goofy-fullnote-display-outer');
    document.getElementById('goofy-main').appendChild(this.div);

    const innerDiv = goog.dom.createDom('div', 'goofy-fullnote-display-inner');
    this.div.appendChild(innerDiv);

    const titleDiv = goog.dom.createDom('div', 'goofy-fullnote-title');
    const titleImg = goog.dom.createDom(
        'img', {class: 'goofy-fullnote-logo', src: '/images/warning.svg'});
    titleDiv.appendChild(titleImg);
    titleDiv.appendChild(
        cros.factory.i18n.i18nLabelNode('Factory tests stopped'));
    innerDiv.appendChild(titleDiv);

    const noteDiv = goog.dom.createDom('div', 'goofy-fullnote-note');
    goog.dom.safe.setInnerHtml(noteDiv, this.goofy.getNotesView());
    innerDiv.appendChild(noteDiv);
  }

  /**
   * Disposes of the critical factory notes display.
   */
  dispose() {
    if (this.div) {
      this.div.remove();
      this.div = null;
    }
  }
};

/**
 * The main Goofy UI.
 */
cros.factory.Goofy = class {
  constructor() {
    /**
     * The WebSocket we'll use to communicate with the backend.
     * @type {!goog.net.WebSocket}
     */
    this.ws = new goog.net.WebSocket();

    /**
     * The UUID that we received from Goofy when starting up.
     * @type {?string}
     */
    this.uuid = null;

    /**
     * The currently visible context menu, if any.
     * @type {?goog.ui.PopupMenu}
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
     * @type {!Array<!goog.ui.AdvancedTooltip>}
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
     * @type {!Object<string, !goog.ui.tree.BaseNode>}
     */
    this.pathNodeMap = {};

    /**
     * A map from test path to the entry in the test list for that test.
     * @type {!Object<string, !cros.factory.TestListEntry>}
     */
    this.pathTestMap = {};

    /**
     * A map from test path to the tree node html id for external reference.
     * @type {!Object<string, string>}
     */
    this.pathNodeIdMap = {};

    /**
     * The path of root test.
     * @type {!string}
     */
    this.rootPath = '';

    /**
     * What locale is currently enabled.
     * @type {string}
     */
    this.locale = 'en-US';

    /**
     * UIs for individual test invocations (by UUID).
     * Use a Map to guarantee that the iteration order is same as insertion
     * order.
     * @type {!Map<string, !cros.factory.Invocation>}
     */
    this.invocations = new Map();

    /**
     * Eng mode prompt.
     * @type {?goog.ui.Dialog}
     */
    this.engineeringModeDialog = null;

    /**
     * Force shutdown prompt dialog.
     * @type {?goog.ui.Dialog}
     */
    this.forceShutdownDialog = null;

    /**
     * Shutdown prompt dialog.
     * @type {?goog.ui.Dialog}
     */
    this.shutdownDialog = null;

    /**
     * Visible dialogs.
     * @type {!Array<!goog.ui.Dialog>}
     */
    this.dialogs = [];

    /**
     * Whether eng mode is enabled.
     * @type {boolean}
     */
    this.engineeringMode = false;

    /**
     * SHA1 hash of password to take UI out of operator mode.  If null, eng mode
     * is always enabled.  Defaults to an invalid '?', which means that eng mode
     * cannot be entered (will be set from Goofy's shared_data).
     * @type {?string}
     */
    this.engineeringPasswordSHA1 = '?';

    /**
     * Debug window.
     * @type {!goog.debug.FancyWindow}
     */
    this.debugWindow = new goog.debug.FancyWindow('main');
    this.debugWindow.setEnabled(false);
    this.debugWindow.init();

    /**
     * Various tests lists that can be enabled in engineering mode.
     * @type {!Array<!cros.factory.TestListInfo>}
     */
    this.testLists = [];

    /**
     * All current notes.
     * @type {!Array<!cros.factory.Note>}
     */
    this.notes = [];

    /**
     * The display for notes.
     * @type {?cros.factory.CriticalNoteDisplay}
     */
    this.noteDisplay = null;

    /**
     * The DOM element for console.
     * @type {?Element}
     */
    this.console = null;

    /**
     * The DOM element for terminal window.
     * @type {?Element}
     */
    this.terminal_win = null;

    /**
     * The WebSocket for terminal window.
     * @type {?WebSocket}
     */
    this.terminal_sock = null;

    /**
     * The menu items for Goofy plugin.
     * @type {?Array<!cros.factory.PluginMenuItem>}
     */
    this.pluginMenuItems = null;

    /**
     * The UI manager for invocations.
     * @type {?cros.factory.testUI.Manager}
     */
    this.testUIManager = null;

    /**
     * The type of UI manager.
     * @type {?string}
     */
    this.testUIManagerType = null;

    /**
     * The cached viewport size.
     * @type {?goog.math.Size}
     */
    this.cachedViewportSize = null;

    // Set up magic keyboard shortcuts.
    goog.events.listen(
        window, goog.events.EventType.KEYDOWN, this.keyListener, true, this);

    /**
     * The device manager.
     * @type {!cros.factory.DeviceManager}
     */
    this.deviceManager = new cros.factory.DeviceManager(this);

    if (cros.factory.ENABLE_DIAGNOSIS_TOOL) {
      /**
       * The diagnosis tool (not yet enabled).
       * @type {?cros.factory.DiagnosisTool}
       */
      this.diagnosisTool = new cros.factory.DiagnosisTool(this);
    }
  }

  /**
   * Sets the title of a modal dialog.
   * @param {!goog.ui.Dialog} dialog
   * @param {string|!goog.html.SafeHtml} title
   */
  static setDialogTitle(dialog, title) {
    goog.dom.safe.setInnerHtml(
        goog.asserts.assertElement(dialog.getTitleTextElement()),
        goog.html.SafeHtml.htmlEscapePreservingNewlines(title));
  }

  /**
   * Sets the content of a modal dialog.
   * @param {!goog.ui.Dialog} dialog
   * @param {string|!goog.html.SafeHtml} content
   */
  static setDialogContent(dialog, content) {
    dialog.setSafeHtmlContent(
        goog.html.SafeHtml.htmlEscapePreservingNewlines(content));
  }

  /**
   * Event listener for Ctrl-Alt-keypress.
   * @param {!goog.events.KeyEvent} event
   */
  keyListener(event) {
    // Prevent alt+left, or alt+right to do page navigation.
    if ((event.keyCode === goog.events.KeyCodes.LEFT ||
         event.keyCode === goog.events.KeyCodes.RIGHT) &&
        event.altKey) {
      event.preventDefault();
    }

    if (event.altKey && event.ctrlKey) {
      switch (String.fromCharCode(event.keyCode)) {
        case '0':
          if (!this.dialogs.length) {
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
  }

  /**
   * Initializes a splitpane and decorate it on an element.
   * @param {string} id
   * @param {!goog.ui.SplitPane.Orientation} orientation
   * @return {!goog.ui.SplitPane}
   */
  initSplitPane(id, orientation) {
    const splitPane = new goog.ui.SplitPane(
        new goog.ui.Component(), new goog.ui.Component(), orientation);
    const element = goog.asserts.assertElement(document.getElementById(id));
    splitPane.decorate(element);

    // Remove the inline size style set by splitPane.decorate, so resizing works
    // better. Note that the goog-splitpane-{first,second}-container would still
    // have inline size style.
    element.removeAttribute('style');

    // Remove the maximize splitpane when double-click on splitpane handle
    // behavior, since it's pretty easy to misclick, and not very useful.
    const handle = element.querySelector(':scope > .goog-splitpane-handle');
    goog.events.removeAll(handle, 'dblclick');

    return splitPane;
  }

  /**
   * Create a callback object to be passed to test UI manager.
   * @return {!cros.factory.testUI.CallBacks}
   */
  createTestUICallbacks() {
    return {
      /**
       * @param {string} path
       * @param {boolean} visible
       */
      notifyTestVisible: (path, visible) => {
        // Change the background color of the node in tree.
        const elt = this.pathNodeMap[path].getElement();
        elt.classList.toggle('goofy-test-visible', visible);
      },

      /**
       * @param {!HTMLIFrameElement} iframe
       */
      tryFocusIFrame: (iframe) => {
        this.tryFocusIFrame(iframe);
      }
    };
  }

  /**
   * Initializes the split panes and the test ui.
   */
  initUIComponents() {
    const viewportSize = goog.dom.getViewportSize(goog.dom.getWindow(document));

    const topSplitPane = this.initSplitPane(
        'goofy-splitpane', goog.ui.SplitPane.Orientation.HORIZONTAL);
    topSplitPane.setFirstComponentSize(Math.max(
        cros.factory.CONTROL_PANEL_MIN_WIDTH,
        viewportSize.width * cros.factory.CONTROL_PANEL_WIDTH_FRACTION));

    const mainAndConsole = this.initSplitPane(
        'goofy-main-and-console', goog.ui.SplitPane.Orientation.VERTICAL);
    mainAndConsole.setFirstComponentSize(
        viewportSize.height -
        Math.max(
            cros.factory.LOG_PANE_MIN_HEIGHT,
            viewportSize.height * cros.factory.LOG_PANE_HEIGHT_FRACTION));

    goog.debug.catchErrors(({
                             /** string */ fileName,
                             /** string */ line,
                             /** string */ message
                           }) => {
      try {
        this.logToConsole(
            `JavaScript error (${fileName}, line ${line}): ${message}`,
            'goofy-internal-error');
      } catch (e) {
        // Oof... error while logging an error!  Maybe the DOM isn't set
        // up properly yet; just ignore.
      }
    });

    window.addEventListener('unhandledrejection', (event) => {
      try {
        this.logToConsole(
            `Unhandled promise rejection: ${event.reason}`,
            'goofy-internal-error');
      } catch (e) {
        // Oof... error while logging an error!  Maybe the DOM isn't set
        // up properly yet; just ignore.
      }
    });

    const fixSplitPaneSize = (/** !goog.ui.SplitPane */ splitPane) => {
      splitPane.setFirstComponentSize(splitPane.getFirstComponentSize());
    };

    // Recalculate the sub-container size when the window is resized.
    this.cachedViewportSize = viewportSize;
    goog.events.listen(window, goog.events.EventType.RESIZE, () => {
      fixSplitPaneSize(topSplitPane);

      // To fix the main and console panel size, we need to re-calculate the
      // size of the main container manually.
      const prevConsoleHeight = this.cachedViewportSize.height
                                - mainAndConsole.getFirstComponentSize();
      const currViewportSize =
          goog.dom.getViewportSize(goog.dom.getWindow(document));
      const currMainHeight = Math.max(
          0, currViewportSize.height - prevConsoleHeight);
      mainAndConsole.setFirstComponentSize(currMainHeight);

      this.cachedViewportSize = currViewportSize;
    });

    goog.events.listen(
        topSplitPane, goog.ui.SplitPane.EventType.HANDLE_DRAG, () => {
          fixSplitPaneSize(mainAndConsole);
        });

    // Disable context menu except in engineering mode.
    goog.events.listen(
        window, goog.events.EventType.CONTEXTMENU,
        (/** !goog.events.Event */ event) => {
          if (!this.engineeringMode) {
            event.stopPropagation();
            event.preventDefault();
          }
        });

    // Whenever we get focus, try to focus any visible iframe (if there's no
    // dialog or context menu).
    goog.events.listen(window, goog.events.EventType.FOCUS, () => {
      this.focusInvocation();
    });

    this.setTestUILayout('tab', {});

    this.console =
        goog.asserts.assertElement(document.getElementById('goofy-console'));
  }

  /**
   * Sets the test UI layout to use.
   * @param {string} type the type of layout, should be ['tab', 'tiled'].
   * @param {!Object} options
   */
  setTestUILayout(type, options) {
    goog.asserts.assert(['tab', 'tiled'].includes(type));
    goog.asserts.assert(this.invocations.size === 0);
    if (type !== this.testUIManagerType) {
      if (this.testUIManager) {
        this.testUIManager.dispose();
      }

      const testUIMainDiv = goog.asserts.assertElement(
          document.getElementById('goofy-test-ui-main'));

      if (type === 'tab') {
        this.testUIManager = new cros.factory.testUI.TabManager(
            testUIMainDiv, this.createTestUICallbacks());
      } else if (type === 'tiled') {
        this.testUIManager = new cros.factory.testUI.TileManager(
            testUIMainDiv, this.createTestUICallbacks());
      }
      this.testUIManagerType = type;
    }
    this.testUIManager.setOptions(options);
  }

  /**
   * Add the invocation to UI manager.
   * @param {!cros.factory.Invocation} invocation
   */
  addInvocationUI(invocation) {
    const {path, iframe} = invocation;
    const label = this.pathTestMap[path].label;
    this.testUIManager.addTestUI(path, label, iframe);
  }

  /**
   * Remove the invocation to UI manager.
   * @param {!cros.factory.Invocation} invocation
   */
  removeInvocationUI(invocation) {
    this.testUIManager.removeTestUI(invocation.path);
  }

  /**
   * Try to focus on an iframe window.
   * Would focus on the iframe if there's no dialog, context menu or terminal.
   * @param {!HTMLIFrameElement} iframe
   */
  tryFocusIFrame(iframe) {
    if (this.dialogs.length || this.contextMenu || this.terminal_win) {
      return;
    }
    iframe.contentWindow.focus();
  }

  /**
   * Returns focus to any visible invocation.
   */
  focusInvocation() {
    // We need a setTimeout(, 0) since the i.iframe.contentWindow.focus()
    // doesn't work directly in the onfocus handler of window.
    setTimeout(() => {
      for (const i of this.invocations.values()) {
        if (i && i.iframe && this.testUIManager.isVisible(i.path)) {
          this.tryFocusIFrame(i.iframe);
          break;
        }
      }
    }, 0);
  }

  /**
   * Initializes the WebSocket.
   */
  initWebSocket() {
    goog.events.listen(this.ws, goog.net.WebSocket.EventType.OPENED, () => {
      this.logInternal('Connection to Goofy opened.');
    });
    goog.events.listen(this.ws, goog.net.WebSocket.EventType.ERROR, () => {
      this.logInternal('Error connecting to Goofy.');
    });
    goog.events.listen(this.ws, goog.net.WebSocket.EventType.CLOSED, () => {
      this.logInternal('Connection to Goofy closed.');
    });
    goog.events.listen(
        this.ws, goog.net.WebSocket.EventType.MESSAGE,
        (/** !goog.net.WebSocket.MessageEvent */ event) => {
          this.handleBackendEvent(event.message);
        });
    window.setInterval(
        this.keepAlive.bind(this), cros.factory.KEEP_ALIVE_INTERVAL_MSEC);
    this.ws.open(`ws://${window.location.host}/event`);
  }

  /**
   * Waits for the Goofy backend to be ready, and then starts UI.
   */
  async preInit() {
    while (true) {
      let /** boolean */ isReady = false;
      try {
        isReady = await this.sendRpc('IsReadyForUIConnection');
      } catch (e) {
        // There's a chance that goofy RPC isn't ready before this, since we
        // initialize goofy RPC server after static files.
        // We can't change the initialization order, since the static page need
        // to be initialized early to prevent Chrome from getting a 404 page for
        // index.html.
      }
      if (isReady) {
        await this.init();
        return;
      }
      window.console.log('Waiting for the Goofy backend to be ready...');
      await cros.factory.utils.delay(500);
    }
  }

  /**
   * Starts the UI.
   */
  async init() {
    try {
      this.initUIComponents();
      await this.initLocaleSelector();
      const testList = await this.sendRpc('GetTestList');
      await this.setTestList(testList);
      this.initWebSocket();
    } finally {
      // Hide the "Loading..." screen even if there's error when initialize
      // previous items, so the exception is shown on screen and easier to
      // know what went wrong.
      document.getElementById('goofy-div-wait').style.display = 'none';
    }

    await Promise.all([
      (async () => {
        this.testLists = await this.sendRpc('GetTestLists');
      })(),
      (async () => {
        this.pluginMenuItems = await this.sendRpc('GetPluginMenuItems');
      })(),
      (async () => {
        const configs = await this.sendRpc('GetPluginFrontendConfigs');
        this.setPluginUI(configs);
      })(),
      (async () => {
        const notes =
            await this.sendRpc('DataShelfGetValue', 'factory_note', true);
        this.updateNote(notes);
      })(),
      (async () => {
        const options =
            await this.sendRpc('DataShelfGetValue', 'test_list_options', true);
        this.engineeringPasswordSHA1 =
            options ? options['engineering_password_sha1'] : null;
        // If no password, enable eng mode, and don't show the 'disable'
        // link, since there is no way to enable it.
        goog.style.setElementShown(
            document.getElementById('goofy-disable-engineering-mode'),
            this.engineeringPasswordSHA1 != null);
        this.setEngineeringMode(this.engineeringPasswordSHA1 == null);
      })(),
      (async () => {
        const error =
            await this.sendRpc('DataShelfGetValue', 'startup_error', true);
        if (error) {
          const alertHtml = goog.html.SafeHtml.concat(
              cros.factory.i18n.i18nLabel(
                  'An error occurred while starting the factory test system\n' +
                  'Factory testing cannot proceed.'),
              goog.html.SafeHtml.create(
                  'div', {class: 'goofy-startup-error'}, error));
          this.alert(alertHtml);
        }
      })()
    ]);
  }

  /**
   * Sets the locale of Goofy.
   * @param {string} locale
   */
  async setLocale(locale) {
    this.locale = locale;
    this.updateCSSClasses();
    await this.sendRpc('DataShelfSetValue', 'ui_locale', this.locale);
  }

  /**
   * Sets up the locale selector.
   */
  async initLocaleSelector() {
    const rootNode = goog.asserts.assertElement(
        document.getElementById('goofy-locale-selector'));

    const localeNames = cros.factory.i18n.getLocaleNames();
    const locales = cros.factory.i18n.locales;

    if (locales.length === 2) {
      const [locale0, locale1] = locales;
      // There are only two locales, a simple toggle button is enough.
      let label = cros.factory.i18n.stringFormat(
          _('Switch to\n{target_locale}'), {target_locale: localeNames});

      // We have to swap the two values, so we show the other locale's prompt
      // when in one locale.
      const value0 = label[locale0];
      const value1 = label[locale1];
      label[locale0] = value1;
      label[locale1] = value0;

      rootNode.appendChild(goog.dom.createDom(
          'div', {class: 'goofy-locale-toggle'},
          cros.factory.i18n.i18nLabelNode(label)));
      goog.events.listen(rootNode, goog.events.EventType.CLICK, () => {
        const locale = this.locale === locale0 ? locale1 : locale0;
        this.setLocale(locale);
      });
    } else if (locales.length > 2) {
      // Show a dropdown menu for locale selection.
      rootNode.appendChild(goog.dom.createDom(
          'div', {class: 'goofy-locale-dropdown'},
          cros.factory.i18n.i18nLabelNode('Language')));
      goog.events.listen(
          rootNode,
          [goog.events.EventType.MOUSEDOWN, goog.events.EventType.CONTEXTMENU],
          (/** !goog.events.Event */ event) => {
            event.stopPropagation();
            event.preventDefault();

            // We reuse the same lastContextMenu{Path, HideTime} with
            // showTestPopup. Choose some path that would never collide with any
            // test.
            const localeSelectorPath = '..fake.path.localeSelector';
            const menu = new goog.ui.PopupMenu();
            if (!this.registerMenu(menu, localeSelectorPath)) {
              menu.dispose();
              return;
            }

            for (const locale of locales) {
              const item = new goog.ui.MenuItem(localeNames[locale]);
              goog.events.listen(
                  item, goog.ui.Component.EventType.ACTION, () => {
                    this.setLocale(locale);
                  });
              menu.addChild(item, true);
            }

            menu.render();
            menu.showAtElement(
                rootNode, goog.positioning.Corner.BOTTOM_LEFT,
                goog.positioning.Corner.TOP_LEFT);
          });
    }

    this.updateCSSClasses();
    const /** string */ locale =
        await this.sendRpc('DataShelfGetValue', 'ui_locale');
    this.locale = locale;
    this.updateCSSClasses();
  }

  /**
   * Create an invocation for a test.
   * @param {string} path
   * @param {string} invocationUuid
   * @return {!cros.factory.Invocation} the invocation.
   */
  createInvocation(path, invocationUuid) {
    cros.factory.logger.info(
        `Creating UI for test ${path} (invocation ${invocationUuid})`);
    const invocation = new cros.factory.Invocation(this, path, invocationUuid);
    this.invocations.set(invocationUuid, invocation);
    return invocation;
  }

  /**
   * Updates classes in a document based on the current settings.
   * @param {!Document} doc
   */
  updateCSSClassesInDocument(doc) {
    const body = doc.body;
    if (body) {
      for (const locale of cros.factory.i18n.locales) {
        body.classList.toggle(`goofy-locale-${locale}`, locale === this.locale);
      }
      body.classList.toggle('goofy-engineering-mode', this.engineeringMode);
      body.classList.toggle('goofy-operator-mode', !this.engineeringMode);
    }
  }

  /**
   * Updates classes in the UI based on the current settings.
   */
  updateCSSClasses() {
    this.updateCSSClassesInDocument(document);
    document.getElementById('goofy-terminal')
        .classList.toggle('goofy-engineering-mode', this.engineeringMode);
    for (const i of this.invocations.values()) {
      if (i && i.iframe && i.iframe.contentDocument) {
        this.updateCSSClassesInDocument(i.iframe.contentDocument);
      }
    }
    for (const i of /** @type {!NodeList<!HTMLIFrameElement>} */ (
             document.querySelectorAll('.goofy-plugin iframe'))) {
      if (i.contentDocument) {
        this.updateCSSClassesInDocument(i.contentDocument);
      }
    }
  }

  /**
   * Updates notes.
   * @param {?Array<!cros.factory.Note>} notes
   */
  updateNote(notes) {
    notes = notes || [];
    this.notes = notes;
    const currentLevel = notes.length ? notes[notes.length - 1].level : '';

    for (const {name} of cros.factory.NOTE_LEVEL) {
      document.getElementById('goofy-logo')
          .classList.toggle(
              `goofy-note-${name.toLowerCase()}`, currentLevel === name);
    }

    if (this.noteDisplay) {
      this.noteDisplay.dispose();
      this.noteDisplay = null;
    }

    if (currentLevel === 'CRITICAL') {
      this.noteDisplay = new cros.factory.CriticalNoteDisplay(this);
    } else if (currentLevel === 'WARNING') {
      this.viewNotes();
    }
  }

  /**
   * Gets factory notes list.
   * @return {!goog.html.SafeHtml}
   */
  getNotesView() {
    const createRowHTML = ({timestamp, name, text}) => {
      const d = new Date(0);
      d.setUTCSeconds(timestamp);
      return goog.html.SafeHtml.create('tr', {}, [
        goog.html.SafeHtml.create(
            'td', {}, cros.factory.Goofy.MDHMS_TIME_FORMAT.format(d)),
        goog.html.SafeHtml.create('th', {}, name),
        goog.html.SafeHtml.create('td', {}, text)
      ]);
    };
    const rows = this.notes.map(createRowHTML).reverse();
    return goog.html.SafeHtml.create('table', {id: 'goofy-note-list'}, rows);
  }

  /**
   * Displays a dialog of notes.
   */
  viewNotes() {
    if (!this.notes.length) {
      return;
    }

    this.createSimpleDialog('Factory Notes', this.getNotesView())
        .setVisible(true);
  }

  /**
   * Registers a dialog. Sets the dialog setDisposeOnHide to true, and returns
   * focus to any running invocation when the dialog is hidden/disposed.
   * @param {!goog.ui.Dialog} dialog
   */
  registerDialog(dialog) {
    this.dialogs.push(dialog);
    dialog.setDisposeOnHide(true);

    goog.events.listen(dialog, goog.ui.Component.EventType.SHOW, () => {
      // Hack: if the dialog contains an input element or button, focus it. (For
      // instance, Prompt only calls select(), not focus(), on the text field,
      // which causes ESC and Enter shortcuts not to work.)
      const elt = dialog.getElement();
      let inputs = elt.getElementsByTagName('input');
      if (!inputs.length) {
        inputs = elt.getElementsByTagName('button');
      }
      if (inputs.length) {
        inputs[0].focus();
      }
    });

    goog.events.listen(dialog, goog.ui.Component.EventType.HIDE, () => {
      goog.array.remove(this.dialogs, dialog);
      this.focusInvocation();
    });
  }

  /**
   * Registers a context menu. Returns focus to any running invocation when the
   * menu is hidden/disposed. Return false if the menu is hid recently.
   * @param {!goog.ui.PopupMenu} menu
   * @param {string} path
   * @return {boolean}
   */
  registerMenu(menu, path) {
    if (path === this.lastContextMenuPath &&
        (+new Date() - this.lastContextMenuHideTime <
         goog.ui.PopupBase.DEBOUNCE_DELAY_MS)) {
      // We just hid it; don't reshow.
      return false;
    }

    // Hide all tooltips so that they don't fight with the context menu.
    this.hideTooltips();

    this.contextMenu = menu;
    this.lastContextMenuPath = path;
    goog.events.listen(menu, goog.ui.Component.EventType.HIDE, (event) => {
      if (event.target !== menu) {
        // We also receive HIDE events for submenus, but we're interested
        // only in events for this top-level menu.
        return;
      }
      menu.dispose();
      this.contextMenu = null;
      this.lastContextMenuHideTime = +new Date();
      // Return focus to visible test, if any.
      this.focusInvocation();
    });
    return true;
  }

  /**
   * Creates a simple dialog with an ok button.
   * @param {string|!goog.html.SafeHtml} title
   * @param {string|!cros.factory.i18n.TranslationDict|!goog.html.SafeHtml}
   *     content
   * @return {!goog.ui.Dialog}
   */
  createSimpleDialog(title, content) {
    const dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);

    dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
    dialog.setModal(false);

    cros.factory.Goofy.setDialogTitle(dialog, title);
    let /** !goog.html.SafeHtml */ html;
    if (content instanceof goog.html.SafeHtml) {
      html = content;
    } else {
      html = cros.factory.i18n.i18nLabel(content);
    }
    cros.factory.Goofy.setDialogContent(dialog, html);

    dialog.getElement().classList.add('goofy-dialog');
    dialog.reposition();
    return dialog;
  }

  /**
   * Displays an alert.
   * @param {string|!cros.factory.i18n.TranslationDict|!goog.html.SafeHtml}
   *     message
   */
  alert(message) {
    const dialog = this.createSimpleDialog('Alert', message);
    dialog.setModal(true);
    dialog.setVisible(true);
  }

  /**
   * Centers an element over the console.
   * @param {?Element} element
   */
  positionOverConsole(element) {
    if (element && this.console) {
      const consoleBound = goog.asserts.assertElement(this.console.parentNode)
                               .getBoundingClientRect();
      const elementBound = element.getBoundingClientRect();
      goog.style.setPosition(
          element,
          consoleBound.left + consoleBound.width / 2 - elementBound.width / 2,
          consoleBound.top + consoleBound.height / 2 - elementBound.height / 2);
    }
  }

  /**
   * Prompts to enter eng mode.
   */
  promptEngineeringPassword() {
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

    this.engineeringModeDialog =
        new goog.ui.Prompt('Password', '', (/** string */ text) => {
          if (!text) {
            return;
          }
          const hash = new goog.crypt.Sha1();
          hash.update(text);
          const digest = goog.crypt.byteArrayToHex(hash.digest());
          if (digest === this.engineeringPasswordSHA1) {
            this.setEngineeringMode(true);
          } else {
            this.alert('Incorrect password.');
          }
        });
    this.registerDialog(this.engineeringModeDialog);
    this.engineeringModeDialog.setVisible(true);
    this.engineeringModeDialog.getElement().classList.add(
        'goofy-engineering-mode-dialog');
    this.engineeringModeDialog.reposition();
    this.positionOverConsole(this.engineeringModeDialog.getElement());
  }

  /**
   * Sets eng mode.
   * @param {boolean} enabled
   */
  setEngineeringMode(enabled) {
    this.engineeringMode = enabled;
    this.updateCSSClasses();
    this.sendRpc('DataShelfSetValue', 'engineering_mode', enabled);
  }

  /**
   * Force DUT to shutdown
   */
  forceShutdown() {
    if (this.forceShutdownDialog) {
      this.forceShutdownDialog.setVisible(false);
      this.forceShutdownDialog.dispose();
      this.forceShutdownDialog = null;
    }
    this.forceShutdownDialog = new goog.ui.Dialog();
    this.registerDialog(this.forceShutdownDialog);
    cros.factory.Goofy.setDialogContent(
      this.forceShutdownDialog,
      cros.factory.i18n.i18nLabel('Press OK to shutdown'));

    goog.events.listen(
      this.forceShutdownDialog, goog.ui.Dialog.EventType.SELECT,
      (/** !goog.ui.Dialog.Event */ e) => {
        if (e.key === goog.ui.Dialog.DefaultButtonKeys.OK) {
          this.sendRpc('Shutdown', 'force_halt');
        }
      });

    this.forceShutdownDialog.setVisible(true);
    this.forceShutdownDialog.reposition();
  }

  /**
   * Deals with data about a pending reboot.
   * @param {?cros.factory.PendingShutdownEvent} shutdownInfo
   */
  setPendingShutdown(shutdownInfo) {
    if (this.shutdownDialog) {
      this.shutdownDialog.setVisible(false);
      this.shutdownDialog.dispose();
      this.shutdownDialog = null;
    }
    if (!shutdownInfo || !shutdownInfo.operation) {
      return;
    }

    const action = shutdownInfo.operation == 'reboot' ? _('Rebooting') :
                                                        _('Shutting down');

    const timesText = shutdownInfo.iterations == 1 ?
        _('once') :
        cros.factory.i18n.stringFormat(
            _('{count} of {total} times'),
            {count: shutdownInfo.iteration, total: shutdownInfo.iterations});

    this.shutdownDialog = new goog.ui.Dialog();
    this.registerDialog(this.shutdownDialog);
    const messageDiv = goog.dom.createDom('div');
    this.shutdownDialog.getContentElement().appendChild(messageDiv);

    const progressBar = new goog.ui.ProgressBar();
    progressBar.render(this.shutdownDialog.getContentElement());

    const startTime = +new Date() / 1000;
    const endTime = startTime + shutdownInfo.delay_secs;
    const shutdownDialog = this.shutdownDialog;

    const tick = () => {
      const now = +new Date() / 1000;

      if (now < endTime) {
        const fraction = (now - startTime) / (endTime - startTime);
        progressBar.setValue(goog.math.clamp(fraction, 0, 1) * 100);

        const secondsLeft = 1 + Math.floor(Math.max(0, endTime - now));
        goog.dom.safe.setInnerHtml(
            messageDiv,
            cros.factory.i18n.i18nLabel(
                _('{action} in {seconds_left} seconds ({times_text}).\n' +
                      'To cancel, press the Escape key.',
                  {action, times_text: timesText, seconds_left: secondsLeft})));
      } else if (now - endTime < shutdownInfo.wait_shutdown_secs) {
        cros.factory.Goofy.setDialogContent(
            shutdownDialog, cros.factory.i18n.i18nLabel('Shutting down...'));
      } else {
        this.setPendingShutdown(null);
      }
    };
    tick();

    const timer = new goog.Timer(20);
    goog.events.listen(timer, goog.Timer.TICK, tick);
    timer.start();

    goog.events.listen(
        this.shutdownDialog, goog.ui.PopupBase.EventType.BEFORE_HIDE, () => {
          timer.dispose();
        });

    goog.events.listen(
        this.shutdownDialog.getElement(), goog.events.EventType.KEYDOWN,
        (/** goog.events.KeyEvent */ e) => {
          if (e.keyCode === goog.events.KeyCodes.ESC) {
            this.cancelShutdown();
          }
        });

    const buttonSet = new goog.ui.Dialog.ButtonSet();
    buttonSet.set(
        goog.ui.Dialog.DefaultButtonKeys.CANCEL,
        cros.factory.i18n.i18nLabelNode('Cancel'), true, true);
    this.shutdownDialog.setButtonSet(buttonSet);

    goog.events.listen(
        this.shutdownDialog, goog.ui.Dialog.EventType.SELECT,
        (/** goog.ui.Dialog.Event */ e) => {
          if (e.key === goog.ui.Dialog.DefaultButtonKeys.CANCEL) {
            this.cancelShutdown();
          }
        });

    this.shutdownDialog.setHasTitleCloseButton(false);
    this.shutdownDialog.setEscapeToCancel(false);
    this.shutdownDialog.getElement().classList.add('goofy-shutdown-dialog');
    this.shutdownDialog.setVisible(true);
    goog.events.listen(
        this.shutdownDialog.getElement(), goog.events.EventType.BLUR, () => {
          goog.Timer.callOnce(
              this.shutdownDialog.focus.bind(this.shutdownDialog));
        });
  }

  /**
   * Cancels a pending shutdown.
   */
  cancelShutdown() {
    this.sendEvent('goofy:cancel_shutdown', {});
    // Wait for Goofy to reset the pending_shutdown data.
  }

  /**
   * Does "auto-run": run all tests that have not yet passed.
   */
  startAutoTest() {
    this.sendEvent(
        'goofy:run_tests_with_status',
        {'status': ['UNTESTED', 'ACTIVE', 'FAILED', 'FAILED_AND_WAIVED']});
  }

  /**
   * Makes a menu item for a context-sensitive menu.
   * @param {string|!cros.factory.i18n.TranslationDict} text the text to
   *     display for non-leaf node.
   * @param {string|!cros.factory.i18n.TranslationDict} text_leaf the text to
   *     display for leaf node.
   * @param {number} count the number of tests.
   * @param {!cros.factory.TestListEntry} test the root node containing the
   *     tests.
   * @param {function(!goog.events.Event)} handler the handler function (see
   *     goog.events.listen).
   * @return {!goog.ui.MenuItem}
   */
  makeMenuItem(text, text_leaf, count, test, handler) {
    const test_label = cros.factory.i18n.translated(test.label);

    const item = new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(
        _(test.subtests.length ? text : text_leaf, {count, test: test_label})));
    item.setEnabled(count !== 0);
    goog.events.listen(
        item, goog.ui.Component.EventType.ACTION, handler, true, this);
    return item;
  }

  /**
   * Returns true if all tests in the test lists before a given test have been
   * run.
   * @param {!cros.factory.TestListEntry} test
   * @return {boolean}
   */
  allTestsRunBefore(test) {
    const root = goog.asserts.assert(this.pathTestMap[this.rootPath]);

    // Create a stack containing only the root node, and walk through it
    // depth-first.  (Use a stack rather than recursion since we want to be able
    // to bail out easily when we hit 'test' or an incomplete test.)
    const /** !Array<!cros.factory.TestListEntry> */ stack = [root];
    while (stack) {
      const item = stack.pop();
      if (item === test) {
        return true;
      }
      if (item.subtests.length) {
        // Append elements in right-to-left order so we will examine them in the
        // correct order.
        stack.push(...item.subtests.slice().reverse());
      } else {
        if (item.state.status === 'ACTIVE' ||
            item.state.status === 'UNTESTED') {
          return false;
        }
      }
    }
    // We should never reach this, since it means that we never saw test while
    // iterating!
    throw Error('Test not in test list');
  }

  /**
   * Displays a context menu for a test in the test tree.
   * @param {string} path the path of the test whose context menu should be
   *     displayed.
   * @param {!Element} labelElement the label element of the node in the test
   *     tree.
   * @param {!Array<!goog.ui.Control>=} extraItems items to prepend to the
   *     menu.
   * @return {boolean}
   */
  showTestPopup(path, labelElement, extraItems) {
    const test = this.pathTestMap[path];

    const menu = new goog.ui.PopupMenu();
    if (!this.registerMenu(menu, path)) {
      menu.dispose();
      return false;
    }

    const addSeparator = () => {
      if (menu.getChildCount() &&
          !(menu.getChildAt(menu.getChildCount() - 1) instanceof
            goog.ui.MenuSeparator)) {
        menu.addChild(new goog.ui.MenuSeparator(), true);
      }
    };

    let numLeaves = 0;
    const /** !Object<string, number> */ numLeavesByStatus = {};
    const allPaths = [];
    let activeAndDisableAbort = false;

    const countLeaves = (/** !cros.factory.TestListEntry */ test) => {
      allPaths.push(test.path);
      for (const subtest of test.subtests) {
        countLeaves(subtest);
      }

      if (!test.subtests.length) {
        ++numLeaves;
        numLeavesByStatus[test.state.status] =
            1 + (numLeavesByStatus[test.state.status] || 0);
        // If there is any subtest that is active and can not be aborted, this
        // test can not be aborted.
        if (test.state.status === 'ACTIVE' && test.disable_abort) {
          activeAndDisableAbort = true;
        }
      }
    };
    countLeaves(test);

    if (this.noteDisplay) {
      const item = new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(
          'Critical factory note; cannot run tests'));
      menu.addChild(item, true);
      item.setEnabled(false);
    } else if (!this.engineeringMode && !this.allTestsRunBefore(test)) {
      const item = new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(
          'Not in engineering mode; cannot skip tests'));
      menu.addChild(item, true);
      item.setEnabled(false);
    } else {
      if (this.engineeringMode ||
          (!test.subtests.length && test.state.status !== 'PASSED')) {
        // Allow user to restart all tests under a particular node if
        // (a) in engineering mode, or (b) if this is a single non-passed test.
        // If neither of these is true, it's too easy to accidentally re-run a
        // bunch of tests and wipe their state.
        const allUntested = numLeavesByStatus['UNTESTED'] === numLeaves;
        const handler = () => {
          this.sendEvent('goofy:restart_tests', {path});
        };
        if (allUntested) {
          menu.addChild(
              this.makeMenuItem(
                  _('Run all {count} tests in "{test}"'),
                  _('Run test "{test}"'), numLeaves, test, handler),
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
        const /** !Array<string> */ status =
            ['UNTESTED', 'ACTIVE', 'FAILED', 'FAILED_AND_WAIVED'];
        let /** number */ count = 0;
        for (const s of status) {
          count += numLeavesByStatus[s] || 0;
        }
        // Only show for parents.
        menu.addChild(
            this.makeMenuItem(
                _('Restart {count} tests in "{test}" that have not passed'), '',
                count, test,
                () => {
                  this.sendEvent('goofy:run_tests_with_status', {status, path});
                }),
            true);
      }

      if (this.engineeringMode) {
        menu.addChild(
            this.makeMenuItem(
                _('Clear status of {count} tests in "{test}"'),
                _('Clear status of test "{test}"'), numLeaves, test,
                () => {
                  this.sendEvent('goofy:clear_state', {path});
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
                () => {
                  this.sendEvent('goofy:auto_run', {path});
                }),
            true);
      }
    }
    addSeparator();

    const stopAllItem =
        new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode('Stop all tests'));
    stopAllItem.setEnabled(numLeavesByStatus['ACTIVE'] > 0);
    goog.events.listen(stopAllItem, goog.ui.Component.EventType.ACTION, () => {
      this.sendEvent(
          'goofy:stop', {'fail': true, 'reason': 'Operator requested abort'});
    });
    menu.addChild(stopAllItem, true);

    // When there is any active test, enable abort item in menu if goofy is in
    // engineering mode or there is no active subtest with disable_abort=true.
    if (numLeavesByStatus['ACTIVE'] &&
        (this.engineeringMode || !activeAndDisableAbort)) {
      menu.addChild(
          this.makeMenuItem(
              _('Abort {count} active tests in "{test}" and continue testing'),
              _('Abort active test "{test}" and continue testing'),
              numLeavesByStatus['ACTIVE'], test,
              () => {
                this.sendEvent('goofy:stop', {
                  'path': path,
                  'fail': true,
                  'reason': 'Operator requested abort'
                });
              }),
          true);
    }

    if (!test.subtests.length && test.state.status === 'ACTIVE') {
      addSeparator();
      const item =
          new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode('Show test UI'));
      goog.events.listen(item, goog.ui.Component.EventType.ACTION, () => {
        this.testUIManager.showTest(test.path);
      });
      item.setEnabled(!this.testUIManager.isVisible(test.path));
      menu.addChild(item, true);
    }

    if (this.engineeringMode && !test.subtests.length) {
      addSeparator();
      menu.addChild(this.createDebugMenu(path), true);
    }

    if (extraItems && extraItems.length) {
      addSeparator();
      for (const item of extraItems) {
        menu.addChild(item, true);
      }
    }

    menu.render(document.body);
    menu.showAtElement(
        labelElement, goog.positioning.Corner.BOTTOM_LEFT,
        goog.positioning.Corner.TOP_LEFT);
    return true;
  }

  /**
   * Create a scrollable goog.ui.SubMenu.
   * The menu of returned SubMenu can be scrolled when the menu is too long.
   * @param {!goog.ui.ControlContent} content the content passed to constructor
   *     of goog.ui.SubMenu.
   * @return {!goog.ui.SubMenu}
   */
  createScrollableSubMenu(content) {
    const subMenu = new goog.ui.SubMenu(content);
    goog.dom.safe.setStyle(
        /** @type {!Element} */ (subMenu.getMenu().getElement()),
        goog.html.SafeStyle.create({overflow: 'scroll'}));
    // Override the positionSubMenu function of subMenu to use RESIZE_HEIGHT, so
    // it would resize the subMenu's menu when it's too long to fit in the
    // viewport.
    subMenu.positionSubMenu = function() {
      goog.ui.SubMenu.prototype.positionSubMenu.apply(this);
      const position = new goog.positioning.AnchoredViewportPosition(
          this.getElement(), goog.positioning.Corner.TOP_END, true);
      /**
       * @suppress {accessControls}
       * @param {number} status the status of the last positionAtAnchor call.
       * @param {!goog.positioning.Corner} corner the corner to adjust.
       * @return {!goog.positioning.Corner}
       */
      position.adjustCorner = (status, corner) => {
        if (status & goog.positioning.OverflowStatus.FAILED_HORIZONTAL) {
          corner = goog.positioning.flipCornerHorizontal(corner);
        }
        // Prefer to anchor to bottom corner, since it works better with
        // RESIZE_HEIGHT when there's little space downward.
        if (status & goog.positioning.OverflowStatus.FAILED_VERTICAL &&
            !(corner & goog.positioning.CornerBit.BOTTOM)) {
          corner = goog.positioning.flipCornerVertical(corner);
        }
        return corner;
      };
      position.setLastResortOverflow(
          goog.positioning.Overflow.ADJUST_X |
          goog.positioning.Overflow.ADJUST_Y |
          goog.positioning.Overflow.RESIZE_HEIGHT);
      position.reposition(
          this.getMenu().getElement(), goog.positioning.Corner.TOP_START);
    }.bind(subMenu);
    return subMenu;
  }

  /**
   * Returns a "Debug" submenu for a given test path.
   * @param {string} path
   * @return {!goog.ui.SubMenu}
   */
  createDebugMenu(path) {
    const subMenu = this.createScrollableSubMenu('Debug');
    const loadingItem = new goog.ui.MenuItem('Loading...');
    loadingItem.setEnabled(false);
    subMenu.addItem(loadingItem);

    (async () => {
      const history = await this.sendRpc('GetTestHistory', path);
      if (!history.length) {
        loadingItem.setCaption('No logs available');
        return;
      }

      if (subMenu.getMenu().indexOfChild(loadingItem) >= 0) {
        subMenu.getMenu().removeChild(loadingItem, true);
      }

      // Arrange in descending order of time (it is returned in ascending
      // order).
      history.reverse();

      let count = history.length;
      for (const entry of history) {
        const status = entry.status ? entry.status.toLowerCase() : 'started';
        let title = `${count}.`;
        count--;

        if (entry.startTime) {
          // TODO(jsalz): Localize (but not that important since this is not
          // for operators)

          title += ` Run at ${
              cros.factory.Goofy.HMS_TIME_FORMAT.format(
                  new Date(entry.startTime * 1000))}`;
        }
        title += ` (${status}`;

        const time = entry.endTime || entry.startTime;
        if (time) {
          let secondsAgo = +new Date() / 1000 - time;

          const hoursAgo = Math.floor(secondsAgo / 3600);
          secondsAgo -= hoursAgo * 3600;

          const minutesAgo = Math.floor(secondsAgo / 60);
          secondsAgo -= minutesAgo * 60;

          if (hoursAgo) {
            title += ` ${hoursAgo} h`;
          }
          if (minutesAgo) {
            title += ` ${minutesAgo} m`;
          }
          title += ` ${Math.floor(secondsAgo)} s ago`;
        }
        title += ')…';

        const item = new goog.ui.MenuItem(goog.dom.createDom(
            'span', `goofy-debug-status-${status}`, title));
        goog.events.listen(item, goog.ui.Component.EventType.ACTION, () => {
          this.showHistoryEntry(entry.testName, entry.testRunId);
        });

        subMenu.addItem(item);
      }
    })();

    return subMenu;
  }

  /**
   * Displays a dialog containing logs.
   * @param {string|!cros.factory.i18n.TranslationDict} title
   * @param {string} data text to show in the dialog.
   */
  showLogDialog(title, data) {
    const content = goog.html.SafeHtml.concat(
        goog.html.SafeHtml.create(
            'div', {class: 'goofy-log-data'},
            cros.factory.i18n.i18nLabel(data)),
        goog.html.SafeHtml.create('div', {class: 'goofy-log-time'}));

    const dialog =
        this.createSimpleDialog(cros.factory.i18n.i18nLabel(title), content);

    const dialogContentElement =
        goog.asserts.assertInstanceof(dialog.getContentElement(), HTMLElement);

    const logDataElement = goog.asserts.assertElement(
        dialogContentElement.getElementsByClassName('goofy-log-data')[0]);
    logDataElement.scrollTop = logDataElement.scrollHeight;

    const logTimeElement = goog.asserts.assertElement(
        dialogContentElement.getElementsByClassName('goofy-log-time')[0]);

    const timer = new goog.Timer(1000);
    goog.events.listen(timer, goog.Timer.TICK, () => {
      // Show time in the same format as in the logs
      const timeStr =
          new goog.date.DateTime().toUTCIsoString(true, true).replace(' ', 'T');
      goog.dom.safe.setInnerHtml(
          logTimeElement,
          goog.html.SafeHtml.concat(
              cros.factory.i18n.i18nLabel('System time: '),
              goog.html.SafeHtml.htmlEscape(timeStr)));
    });
    timer.dispatchTick();
    timer.start();
    goog.events.listen(dialog, goog.ui.Component.EventType.HIDE, () => {
      timer.dispose();
    });
    dialog.setVisible(true);
  }

  /**
   * Add a factory note.
   * @param {string} name
   * @param {string} note
   * @param {string} level
   * @return {boolean}
   */
  addNote(name, note, level) {
    if (!name || !note) {
      alert('Both name and note fields must not be empty!');
      return false;
    }
    // The timestamp for Note is set in the RPC call AddNote.
    this.sendRpc('AddNote', new cros.factory.Note(name, note, 0, level));
    return true;
  }

  /**
   * Displays a dialog to modify factory note.
   */
  showNoteDialog() {
    const rows = [];
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create(
          'th', {}, cros.factory.i18n.i18nLabel('Your Name')),
      goog.html.SafeHtml.create(
          'td', {},
          goog.html.SafeHtml.create('input', {id: 'goofy-addnote-name'}))
    ]));
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create(
          'th', {}, cros.factory.i18n.i18nLabel('Note Content')),
      goog.html.SafeHtml.create(
          'td', {},
          goog.html.SafeHtml.create('textarea', {id: 'goofy-addnote-text'}))
    ]));

    const options = [];
    for (const {name, message} of cros.factory.NOTE_LEVEL) {
      const selected = name === 'INFO' ? 'selected' : null;
      options.push(goog.html.SafeHtml.create(
          'option', {value: name, selected}, `${name}: ${message}`));
    }
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create(
          'th', {}, cros.factory.i18n.i18nLabel('Severity')),
      goog.html.SafeHtml.create(
          'td', {},
          goog.html.SafeHtml.create(
              'select', {id: 'goofy-addnote-level'}, options))
    ]));

    const table = goog.html.SafeHtml.create(
        'table', {class: 'goofy-addnote-table'}, rows);
    const buttons = goog.ui.Dialog.ButtonSet.createOkCancel();

    const dialog =
        this.createSimpleDialog(cros.factory.i18n.i18nLabel('Add Note'), table);
    dialog.setModal(true);
    dialog.setButtonSet(buttons);

    const nameBox = goog.asserts.assertInstanceof(
        document.getElementById('goofy-addnote-name'), HTMLInputElement);
    const textBox = goog.asserts.assertInstanceof(
        document.getElementById('goofy-addnote-text'), HTMLTextAreaElement);
    const levelBox = goog.asserts.assertInstanceof(
        document.getElementById('goofy-addnote-level'), HTMLSelectElement);

    goog.events.listen(
        dialog, goog.ui.Dialog.EventType.SELECT,
        (/** !goog.ui.Dialog.Event */ event) => {
          if (event.key === goog.ui.Dialog.DefaultButtonKeys.OK) {
            if (!this.addNote(nameBox.value, textBox.value, levelBox.value)) {
              event.preventDefault();
            }
          }
        });
    dialog.setVisible(true);
  }

  /**
   * Uploads factory logs to the factory server.
   * @param {string} name name of the person uploading logs
   * @param {string} serial serial number of this device
   * @param {string} description bug description
   */
  async uploadFactoryLogs(name, serial, description) {
    const dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    cros.factory.Goofy.setDialogTitle(
        dialog, cros.factory.i18n.i18nLabel('Uploading factory logs...'));
    cros.factory.Goofy.setDialogContent(
        dialog,
        cros.factory.i18n.i18nLabel('Uploading factory logs.  Please wait...'));

    dialog.setButtonSet(null);
    dialog.setVisible(true);

    try {
      const {/** number */ size, /** string */ key} =
          await this.sendRpc('UploadFactoryLogs', name, serial, description);
      cros.factory.Goofy.setDialogContent(
          dialog,
          goog.html.SafeHtml.concat(
              goog.html.SafeHtml.htmlEscapePreservingNewlines(
                  `Success! Uploaded factory logs (${
                      size} bytes).\nThe archive key is `),
              goog.html.SafeHtml.create(
                  'span', {class: 'goofy-ul-archive-key'}, key),
              goog.html.SafeHtml.htmlEscapePreservingNewlines(
                  '.\nPlease use this key when filing bugs\n' +
                  'or corresponding with the factory team.')));
      dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
      dialog.reposition();
    } catch (error) {
      cros.factory.Goofy.setDialogContent(
          dialog, `Unable to upload factory logs:\n${error.message}`);
      dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
      dialog.reposition();
    }
  }

  /**
   * Ask goofy to reload current test list to apply local changes.
   */
  async reloadTestList() {
    try {
      await this.sendRpc('ReloadTestList');
    } catch (error) {
      this.alert(`Failed to reload test list\n${error.message}`);
      throw error;
    }
  }

  /**
   * Displays a dialog to upload factory logs to factory server.
   */
  showUploadFactoryLogsDialog() {
    const dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    dialog.setModal(true);

    const rows = [];
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create(
          'th', {}, cros.factory.i18n.i18nLabel('Your Name')),
      goog.html.SafeHtml.create(
          'td', {},
          goog.html.SafeHtml.create(
              'input', {id: 'goofy-ul-name', size: 30}))
    ]));
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create(
          'th', {}, cros.factory.i18n.i18nLabel('Serial Number')),
      goog.html.SafeHtml.create(
          'td', {},
          goog.html.SafeHtml.create(
              'input', {id: 'goofy-ul-serial', size: 30}))
    ]));
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create(
          'th', {}, cros.factory.i18n.i18nLabel('Bug Description')),
      goog.html.SafeHtml.create(
          'td', {},
          goog.html.SafeHtml.create(
              'input', {id: 'goofy-ul-description', size: 50}))
    ]));

    const table =
        goog.html.SafeHtml.create('table', {class: 'goofy-ul-table'}, rows);
    cros.factory.Goofy.setDialogContent(dialog, table);

    const buttons = goog.ui.Dialog.ButtonSet.createOkCancel();
    dialog.setButtonSet(buttons);

    cros.factory.Goofy.setDialogTitle(
        dialog, cros.factory.i18n.i18nLabel('Upload Factory Logs'));
    dialog.setVisible(true);

    const nameElt = goog.asserts.assertInstanceof(
        document.getElementById('goofy-ul-name'), HTMLInputElement);
    const serialElt = goog.asserts.assertInstanceof(
        document.getElementById('goofy-ul-serial'), HTMLInputElement);
    const descriptionElt = goog.asserts.assertInstanceof(
        document.getElementById('goofy-ul-description'), HTMLInputElement);

    // Enable OK only if all three of these text fields are filled in.
    const /** !Array<HTMLInputElement> */ elts =
        [nameElt, serialElt, descriptionElt];
    const checkOKEnablement = () => {
      buttons.setButtonEnabled(
          goog.ui.Dialog.DefaultButtonKeys.OK, elts.every((elt) => elt.value));
    };
    for (const elt of elts) {
      goog.events.listen(
          elt, [goog.events.EventType.CHANGE, goog.events.EventType.KEYUP],
          checkOKEnablement, false);
    }
    checkOKEnablement();

    goog.events.listen(
        dialog, goog.ui.Dialog.EventType.SELECT,
        (/** !goog.ui.Dialog.Event */ event) => {
          if (event.key !== goog.ui.Dialog.DefaultButtonKeys.OK) {
            return;
          }

          this.uploadFactoryLogs(
                  nameElt.value, serialElt.value, descriptionElt.value)
              .then(() => {
                dialog.dispose();
              });

          event.preventDefault();
        });
  }

  /**
   * Saves factory logs to a USB drive.
   */
  async saveFactoryLogsToUSB() {
    const title = cros.factory.i18n.i18nLabel('Save Factory Logs to USB');

    const doSave = () => {
      const save = async (/** string */ id, /** boolean */ probe) => {
        const dialog = new goog.ui.Dialog();
        this.registerDialog(dialog);
        cros.factory.Goofy.setDialogTitle(dialog, title);
        cros.factory.Goofy.setDialogContent(
            dialog,
            cros.factory.i18n.i18nLabel('Saving factory logs to USB drive...'));
        dialog.setButtonSet(null);
        dialog.setVisible(true);
        this.positionOverConsole(dialog.getElement());
        try {
          const {dev, name: filename, size, temporary} = /**
                * @type {{dev: string, name: string, size: number,
                *     temporary: boolean}}
                */ (await this.sendRpc('SaveLogsToUSB', id, probe));
          if (temporary) {
            cros.factory.Goofy.setDialogContent(
                dialog,
                cros.factory.i18n.i18nLabel(_(
                    'Success! Saved factory logs ({size}) bytes) to {dev} as' +
                        '\n{filename}. The drive has been unmounted.',
                    {size: size.toString(), dev, filename})));
          } else {
            cros.factory.Goofy.setDialogContent(
                dialog,
                cros.factory.i18n.i18nLabel(_(
                    'Success! Saved factory logs ({size}) bytes) to {dev} as' +
                        '\n{filename}.',
                    {size: size.toString(), dev, filename})));
          }
        } catch (error) {
          cros.factory.Goofy.setDialogContent(
              dialog, `Unable to save logs: ${error.message}`);
        }
        dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
        this.positionOverConsole(dialog.getElement());
      };

      const dialog = new goog.ui.Dialog();
      this.registerDialog(dialog);
      dialog.setModal(true);

      const rows = [];
      rows.push(goog.html.SafeHtml.create('tr', {}, [
        goog.html.SafeHtml.create(
            'td', {}, cros.factory.i18n.i18nLabel(
                'Enter an optional identifier for the archive ' +
                '(or press Enter for none):'))
      ]));
      rows.push(goog.html.SafeHtml.create('tr', {}, [
        goog.html.SafeHtml.create(
            'td', {},
            goog.html.SafeHtml.create(
                'input', {id: 'goofy-usblog-id', size: 50}))
      ]));
      rows.push(goog.html.SafeHtml.create('tr', {}, [
        goog.html.SafeHtml.create(
            'td', {}, [
              goog.html.SafeHtml.create(
                  'input', {id: 'goofy-usblog-probe', type: 'checkbox'}),
              cros.factory.i18n.i18nLabel(
                  'Include probe result (takes longer time)')
            ])
      ]));

      const table =
          goog.html.SafeHtml.create(
              'table', {class: 'goofy-usblog-table'}, rows);
      cros.factory.Goofy.setDialogContent(dialog, table);

      const buttons = goog.ui.Dialog.ButtonSet.createOkCancel();
      dialog.setButtonSet(buttons);

      cros.factory.Goofy.setDialogTitle(dialog, title);
      dialog.setVisible(true);

      const idElt = goog.asserts.assertInstanceof(
          document.getElementById('goofy-usblog-id'), HTMLInputElement);
      const probeElt = goog.asserts.assertInstanceof(
          document.getElementById('goofy-usblog-probe'), HTMLInputElement);

      goog.events.listen(
          dialog, goog.ui.Dialog.EventType.SELECT,
          (/** !goog.ui.Dialog.Event */ event) => {
            if (event.key !== goog.ui.Dialog.DefaultButtonKeys.OK) {
              return;
            }
            dialog.dispose();
            save(idElt.value, probeElt.checked);
            event.preventDefault();
          });
    };

    const waitForUSBDialog = new goog.ui.Dialog();
    this.registerDialog(waitForUSBDialog);
    cros.factory.Goofy.setDialogContent(
        waitForUSBDialog,
        cros.factory.i18n.i18nLabel(
            'Please insert a formatted USB stick' +
            ' and wait a moment for it to be mounted.'));
    waitForUSBDialog.setButtonSet(new goog.ui.Dialog.ButtonSet().addButton(
        goog.ui.Dialog.ButtonSet.DefaultButtons.CANCEL, false, true));
    cros.factory.Goofy.setDialogTitle(waitForUSBDialog, title);
    waitForUSBDialog.setVisible(true);
    this.positionOverConsole(waitForUSBDialog.getElement());

    while (waitForUSBDialog.isVisible()) {
      const /** boolean */ available =
          await this.sendRpc('IsUSBDriveAvailable');
      if (available) {
        waitForUSBDialog.dispose();
        doSave();
        return;
      }
      await cros.factory.utils.delay(cros.factory.MOUNT_USB_DELAY_MSEC);
    }
  }

  /**
   * Displays a dialog containing history for a given test invocation.
   * @param {string} path
   * @param {string} invocation
   */
  async showHistoryEntry(path, invocation) {
    const /** !cros.factory.HistoryEntry */ entry =
        await this.sendRpc('GetTestHistoryEntry', path, invocation);

    let testlogObj = {};
    for (const name of ['status', 'startTime', 'time', 'endTime']) {
      if (entry.testlog[name]) {
        let /** string|number */ value = entry.testlog[name];
        delete entry.testlog[name];
        if (name.endsWith('ime')) {
          value = cros.factory.Goofy.FULL_TIME_FORMAT.format(
              new Date(value * 1000));
        }
        testlogObj[name] = value;
      }
    }

    testlogObj = Object.assign(testlogObj, entry.testlog);

    const testlogData = goog.html.SafeHtml.create(
        'div', {class: 'goofy-history-metadata'},
        JSON.stringify(testlogObj, null, 4));

    const title =
        `${entry.testlog.testName} (invocation ${entry.testlog.testRunId})`;

    const content = goog.html.SafeHtml.concat(
        goog.html.SafeHtml.create('div', {class: 'goofy-history'}, [
          goog.html.SafeHtml.create('div', {class: 'goofy-debug-tabbar'}, [
            goog.html.SafeHtml.create(
                'button', {class: 'goofy-debug-tab'}, 'Test Info'),
            goog.html.SafeHtml.create(
                'button', {class: 'goofy-debug-tab'}, 'Log'),
            goog.html.SafeHtml.create(
                'button', {class: 'goofy-debug-tab'}, 'Source Code')
          ]),
          goog.html.SafeHtml.create(
              'div', {class: 'goofy-debug-div'}, testlogData),
          goog.html.SafeHtml.create(
              'div', {class: 'goofy-debug-div'},
              goog.html.SafeHtml.create(
                  'div', {class: 'goofy-history-log'}, entry.log)),
          goog.html.SafeHtml.create(
              'div', {class: 'goofy-debug-div'},
              goog.html.SafeHtml.create(
                  'div', {class: 'goofy-history-code'}, entry.source_code))
        ]));

    const debugDialog = this.createSimpleDialog(title, content);
    debugDialog.getElement().classList.add('goofy-debug-dialog');

    const debugDialogContentElement = debugDialog.getContentElement();

    const tabButton =
        debugDialogContentElement.getElementsByClassName('goofy-debug-tab');

    const debugPart =
        debugDialogContentElement.getElementsByClassName('goofy-debug-div');

    const setVisibility = function(i) {
      for (let j = 0; j < debugPart.length; j++) {
        debugPart[j].classList.add('goofy-debug-div-invisible');
        tabButton[j].classList.remove('goofy-debug-tab-clicked');
      }
      debugPart[i].classList.remove('goofy-debug-div-invisible');
      tabButton[i].classList.add('goofy-debug-tab-clicked');
    };

    for (let i = 0; i < tabButton.length; i++) {
      goog.events.listen(tabButton[i], goog.events.EventType.CLICK, () => {
        setVisibility(i);
      });
    }

    setVisibility(0);
    debugDialog.setVisible(true);
  }

  /**
   * Updates the tooltip for a test based on its status.
   * The tooltip will be displayed only for failed tests.
   * @param {string} path
   * @param {!goog.ui.AdvancedTooltip} tooltip
   */
  updateTestToolTip(path, tooltip) {
    const test = this.pathTestMap[path];
    const tooltipElement =
        goog.asserts.assertInstanceof(tooltip.getElement(), HTMLElement);

    tooltip.setText('');

    const errorMsg = test.state.error_msg;
    if ((test.state.status !== 'FAILED' &&
         test.state.status !== 'FAILED_AND_WAIVED') ||
        this.contextMenu || !errorMsg) {
      // Just show the test path, with a very short hover delay.
      tooltip.setText(test.path);
      tooltip.setHideDelayMs(cros.factory.NON_FAILING_TEST_HOVER_DELAY_MSEC);
    } else {
      // Show the last failure.
      const lines = errorMsg.split('\n');
      const html = [];
      const invocation = test.state.invocation;
      html.push(
          goog.html.SafeHtml.htmlEscape(`${test.path} failed:`),
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
      if (invocation) {
        html.push(goog.html.SafeHtml.create(
            'div', {class: 'goofy-test-failure-debug-link'}, 'Debug...'));
      }

      tooltip.setSafeHtml(goog.html.SafeHtml.concat(html));

      if (lines.length) {
        const link =
            goog.asserts.assertElement(tooltipElement.getElementsByClassName(
                'goofy-test-failure-detail-link')[0]);
        goog.events.listen(link, goog.events.EventType.CLICK, () => {
          tooltipElement.classList.add('goofy-test-failure-expanded');
          tooltip.reposition();
        }, true);
      }
      if (invocation) {
        const link =
            goog.asserts.assertElement(tooltipElement.getElementsByClassName(
                'goofy-test-failure-debug-link')[0]);
        goog.events.listen(link, goog.events.EventType.CLICK, () => {
          tooltip.setVisible(false);
          this.showHistoryEntry(test.path, /** @type {string} */ (invocation));
        });
      }
    }
  }

  /**
   * Sets up the UI for a the test list.  (Should be invoked only once, when the
   * test list is received.)
   * @param {!cros.factory.TestListEntry} testList the test list (the return
   *     value of the GetTestList RPC call).
   */
  async setTestList(testList) {
    cros.factory.logger.info(
        `Received test list: ${goog.debug.expose(testList)}`);
    document.getElementById('goofy-loading').style.display = 'none';

    this.rootPath = testList.path;
    this.addToNode(null, testList);
    // expandAll is necessary to get all the elements to actually be created
    // right away so we can add listeners.  We'll collapse it later.
    this.testTree.expandAll();
    this.testTree.render(document.getElementById('goofy-test-tree'));

    const addListener = (
        /** string */ path, /** !Element */ labelElement,
        /** !Element */ rowElement) => {
      const tooltip = new goog.ui.AdvancedTooltip(rowElement);
      tooltip.setHideDelayMs(1000);
      this.tooltips.push(tooltip);
      goog.events.listen(
          tooltip, goog.ui.Component.EventType.BEFORE_SHOW, () => {
            this.updateTestToolTip(path, tooltip);
          });
      goog.events.listen(
          rowElement, goog.events.EventType.CONTEXTMENU,
          (/** !goog.events.KeyEvent */ event) => {
            if (event.ctrlKey) {
              // Ignore; let the default (browser) context menu show up.
              return;
            }

            this.showTestPopup(path, labelElement);
            event.stopPropagation();
            event.preventDefault();
          });
      goog.events.listen(
          labelElement, goog.events.EventType.MOUSEDOWN,
          (/** !goog.events.KeyEvent */ event) => {
            if (event.button === 0) {
              this.showTestPopup(path, labelElement);
              event.stopPropagation();
              event.preventDefault();
            }
          });
    };

    for (const path of Object.keys(this.pathNodeMap)) {
      const node = this.pathNodeMap[path];
      const labelElement = goog.asserts.assertElement(node.getLabelElement());
      const rowElement = goog.asserts.assertElement(node.getRowElement());
      addListener(path, labelElement, rowElement);
    }

    const buildTitleExtras = () => {
      const extraItems = [];
      const addExtraItem =
          (/** !cros.factory.i18n.TranslationDict */ label,
           /** function() */ action) => {
            const item =
                new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(label));
            goog.events.listen(
                item, goog.ui.Component.EventType.ACTION, action, false, this);
            extraItems.push(item);
          };

      if (this.engineeringMode) {
        addExtraItem(_('Update factory software'), this.updateFactory);
        extraItems.push(this.makeSwitchTestListMenu());
        extraItems.push(new goog.ui.MenuSeparator());
        addExtraItem(_('Save note on device'), this.showNoteDialog);
        addExtraItem(_('View notes'), this.viewNotes);
        addExtraItem(_('Clear notes'), () => this.sendRpc('ClearNotes'));
        extraItems.push(new goog.ui.MenuSeparator());
        if (cros.factory.ENABLE_DIAGNOSIS_TOOL) {
          addExtraItem(
              _('Diagnosis Tool'),
              this.diagnosisTool.showWindow.bind(this.diagnosisTool));
        }
      }

      addExtraItem(
          _('Save factory logs to USB drive...'), this.saveFactoryLogsToUSB);
      addExtraItem(_('Upload factory logs...'), async () => {
        try {
          await this.sendRpc('PingFactoryServer');
        } catch (error) {
          this.alert(`Unable to contact factory server.\n${error.message}`);
          return;
        }
        this.showUploadFactoryLogsDialog();
      });
      addExtraItem(_('DUT Shutdown'), this.forceShutdown);
      addExtraItem(_('Reload Test List'), () => {
        this.reloadTestList();
      });
      addExtraItem(
          _('Toggle engineering mode'), this.promptEngineeringPassword);

      if (this.pluginMenuItems) {
        extraItems.push(new goog.ui.MenuSeparator());
        const engineeringMode = this.engineeringMode;
        for (const item of this.pluginMenuItems) {
          if (item.eng_mode_only && !engineeringMode) {
            continue;
          }
          addExtraItem(item.text, async () => {
            const /** !cros.factory.PluginMenuReturnData */ return_data =
                await this.sendRpc('OnPluginMenuItemClicked', item.id);
            if (return_data.action === 'SHOW_IN_DIALOG') {
              this.showLogDialog(item.text, return_data.data);
            } else if (return_data.action === 'RUN_AS_JS') {
              eval(return_data.data);
            } else {
              this.alert(`Unknown return action: ${return_data.action}`);
            }
          });
        }
      }
      return extraItems;
    };

    for (const eventType of /** @type {!Array<string>} */ ([
           goog.events.EventType.MOUSEDOWN, goog.events.EventType.CONTEXTMENU
         ])) {
      goog.events.listen(
          document.getElementById('goofy-title'), eventType,
          (/** !goog.events.KeyEvent */ event) => {
            if (eventType === goog.events.EventType.MOUSEDOWN &&
                event.button !== 0) {
              // Only process primary button for MOUSEDOWN.
              return;
            }
            if (event.ctrlKey) {
              // Ignore; let the default (browser) context menu show up.
              return;
            }

            const logo = goog.asserts.assertElement(
                document.getElementById('goofy-logo-text'));
            this.showTestPopup(this.rootPath, logo, buildTitleExtras());

            event.stopPropagation();
            event.preventDefault();
          });
    }

    this.testTree.collapseAll();
    const /** !Object<string, !cros.factory.TestState> */ stateMap =
        await this.sendRpc('GetTestStateMap');
    for (const path of Object.keys(stateMap)) {
      if (!path.startsWith('_')) {  // e.g., __jsonclass__
        this.setTestState(path, stateMap[path]);
      }
    }
  }

  /**
   * Create the switch test list menu.
   * @return {!goog.ui.SubMenu}
   */
  makeSwitchTestListMenu() {
    const subMenu = new goog.ui.SubMenu(
        cros.factory.i18n.i18nLabelNode('Switch test list'));
    for (const {name, id, enabled} of this.testLists) {
      const item = new goog.ui.MenuItem(cros.factory.i18n.i18nLabelNode(name));
      item.setSelectable(true);
      item.setSelected(enabled);
      subMenu.addItem(item);
      if (enabled) {
        // Don't do anything if the active one is selected.
        continue;
      }
      goog.events.listen(item, goog.ui.Component.EventType.ACTION, () => {
        const dialog = new goog.ui.Dialog();
        this.registerDialog(dialog);
        const title = cros.factory.i18n.stringFormat(
            _('Switch Test List: {test_list}'), {test_list: name});
        cros.factory.Goofy.setDialogTitle(
            dialog, cros.factory.i18n.i18nLabel(title));
        cros.factory.Goofy.setDialogContent(
            dialog,
            cros.factory.i18n.i18nLabel(_(
                'Warning: Switching to test list "{test_list}"' +
                    ' will clear all test state.\n' +
                    'Are you sure you want to proceed?',
                {test_list: name})));

        const buttonSet = new goog.ui.Dialog.ButtonSet();
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
            (/** !goog.ui.Dialog.Event */ e) => {
              if (e.key === goog.ui.Dialog.DefaultButtonKeys.OK) {
                const dialog = this.showIndefiniteActionDialog(
                    title, _('Switching test list. Please wait...'));
                this.sendRpc('SwitchTestList', id).catch((error) => {
                  dialog.dispose();
                  this.alert(`Unable to switch test list:\n${error.message}`);
                });
              }
            });
      });
    }
    return subMenu;
  }

  /**
   * Displays a dialog for an operation that should never return.
   * @param {string|!cros.factory.i18n.TranslationDict} title
   * @param {string|!cros.factory.i18n.TranslationDict} label
   * @return {!goog.ui.Dialog}
   */
  showIndefiniteActionDialog(title, label) {
    const dialog = new goog.ui.Dialog();
    this.registerDialog(dialog);
    dialog.setHasTitleCloseButton(false);
    cros.factory.Goofy.setDialogTitle(
        dialog, cros.factory.i18n.i18nLabel(title));
    cros.factory.Goofy.setDialogContent(
        dialog, cros.factory.i18n.i18nLabel(label));
    dialog.setButtonSet(null);
    dialog.setVisible(true);
    dialog.reposition();
    return dialog;
  }

  /**
   * Sends an event to update factory software.
   */
  async updateFactory() {
    const dialog = this.showIndefiniteActionDialog(
        _('Software update'), _('Updating factory software. Please wait...'));

    const {success, updated, error_msg: errorMsg} = /**
           * @type {{success: boolean, updated: boolean, error_msg: ?string}}
           */ (await this.sendRpc('UpdateFactory'));
    if (updated) {
      dialog.setTitle('Update succeeded');
      cros.factory.Goofy.setDialogContent(
          dialog, cros.factory.i18n.i18nLabel('Update succeeded. Restarting.'));
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
  }

  /**
   * Sets the state for a particular test.
   * @param {string} path
   * @param {!cros.factory.TestState} state the TestState object (contained in
   *     an event or as a response to the RPC call).
   */
  setTestState(path, state) {
    const node = this.pathNodeMap[path];
    if (!node) {
      goog.log.warning(
          cros.factory.logger, `No node found for test path ${path}`);
      return;
    }

    const elt = goog.asserts.assertElement(node.getElement());
    const test = this.pathTestMap[path];
    test.state = state;

    // Assign the appropriate class to the node, and remove all other status
    // classes.
    cros.factory.utils.removeClassesWithPrefix(elt, 'goofy-status-');
    elt.classList.add(
        `goofy-status-${state.status.toLowerCase().replace(/_/g, '-')}`);

    if (state.status === 'ACTIVE') {
      // Automatically show the test if it is running.
      node.reveal();
    }
  }

  /**
   * Adds a test node to the tree.
   * @param {?goog.ui.tree.BaseNode} parent
   * @param {!cros.factory.TestListEntry} test
   */
  addToNode(parent, test) {
    let node;
    if (parent == null) {
      node = this.testTree;
    } else {
      const html = cros.factory.i18n.i18nLabel(test.label);
      node = this.testTree.createNode();
      node.setSafeHtml(html);
      parent.addChild(node);
    }
    for (const subtest of test.subtests) {
      this.addToNode(node, subtest);
    }

    node.setIconClass('goofy-test-icon');
    node.setExpandedIconClass('goofy-test-icon');

    this.pathNodeMap[test.path] = node;
    this.pathTestMap[test.path] = test;
    this.pathNodeIdMap[test.path] = node.getId();
  }

  /**
   * Sends an event to Goofy.
   * @param {string} type the event type (e.g., 'goofy:hello').
   * @param {!Object} properties of event.
   */
  sendEvent(type, properties) {
    const dict = goog.object.clone(properties);
    dict.type = type;
    // Transform all undefined in object values to null.
    const serialized = JSON.stringify(
        dict, (key, value) => value === undefined ? null : value);
    goog.log.info(cros.factory.logger, `Sending event: ${serialized}`);
    if (this.ws.isOpen()) {
      this.ws.send(serialized);
    }
  }


  /**
   * Calls an RPC function.
   * @param {string} method
   * @param {...?} args
   * @returns {Promise}
   */
  sendRpc(method, ...args) {
    return this.sendRpcImpl_(method, args, '/goofy');
  }

  /**
   * Calls an RPC function for plugin.
   * @param {string} pluginName
   * @param {string} method
   * @param {...?} args
   * @returns {Promise}
   */
  sendRpcToPlugin(pluginName, method, ...args) {
    return this.sendRpcImpl_(
        method, args, `/plugin/${pluginName.replace('.', '_')}`);
  }

  /**
   * Implementation for sendRpc and sendRpcToPlugin.
   * @param {string} method
   * @param {!Array<?Object>} params
   * @param {string} path
   * @returns {Promise}
   * @private
   */
  async sendRpcImpl_(method, params, path) {
    const body = JSON.stringify({method, params, id: 1});
    let response;
    const MAX_RETRY = 5;
    for (let retry = 1; retry <= MAX_RETRY; retry++) {
      try {
        response = await fetch(path, {body, method: 'POST'});
        break;
      } catch (error) {
        if (retry === MAX_RETRY) {
          const message = `RPC error calling ${method}: ${error.message}`;
          this.logToConsole(message, 'goofy-internal-error');
          throw error;
        }
        await cros.factory.utils.delay(100);
      }
    }
    const /** {error: ?{message: string}, result: ?Object} */ json =
        await response.json();
    cros.factory.logger.info(
        `RPC response for ${method}: ${JSON.stringify(json)}`);
    if (json.error) {
      throw new Error(json.error.message);
    }
    return json.result;
  }

  /**
   * Sends a keepalive event if the web socket is open.
   */
  keepAlive() {
    if (this.ws.isOpen()) {
      this.sendEvent('goofy:keepalive', {uuid: this.uuid});
    }
  }

  /**
   * Writes a message to the console log.
   * @param {string} message
   * @param {!Object|!Array<string>|string=} opt_attributes attributes to add
   *     to the div element containing the log entry.
   */
  logToConsole(message, opt_attributes) {
    if (this.console) {
      const div = goog.dom.createDom('div', opt_attributes);
      div.appendChild(document.createTextNode(message));
      this.console.appendChild(div);

      // Restrict the size of the log to avoid UI lag.
      if (this.console.childNodes.length > cros.factory.MAX_LINE_CONSOLE_LOG) {
        this.console.removeChild(this.console.firstChild);
      }

      // Scroll to bottom.  TODO(jsalz): Scroll only if already at the bottom,
      // or add scroll lock.
      this.console.scrollTop = this.console.scrollHeight;
    }
  }

  /**
   * Logs an "internal" message to the console (as opposed to a line from
   * console.log).
   * @param {string} message
   */
  logInternal(message) {
    this.logToConsole(message, 'goofy-internal-log');
  }

  /**
   * Hides tooltips, and cancels pending shows.
   * @suppress {accessControls}
   */
  hideTooltips() {
    for (const tooltip of this.tooltips) {
      tooltip.clearShowTimer();
      tooltip.setVisible(false);
    }
  }

  /**
   * Handles an event sends from the backend.
   * @param {string} jsonMessage the message as a JSON string.
   */
  handleBackendEvent(jsonMessage) {
    goog.log.info(cros.factory.logger, `Got message: ${jsonMessage}`);
    const untypedMessage =
        /** @type {{type: string}} */ (JSON.parse(jsonMessage));
    const messageType = untypedMessage.type;

    switch (messageType) {
      case 'goofy:hello': {
        const message = /** @type {{uuid: string}} */ (untypedMessage);
        if (this.uuid && message.uuid !== this.uuid) {
          // The goofy process has changed; reload the page.
          goog.log.info(cros.factory.logger, 'Incorrect UUID; reloading');
          window.location.reload();
          return;
        } else {
          this.uuid = message.uuid;
          // Send a keepAlive to confirm the UUID with the backend.
          this.keepAlive();
        }
        break;
      }
      case 'goofy:log': {
        const message = /** @type {{message: string}} */ (untypedMessage);
        this.logToConsole(message.message);
        break;
      }
      case 'goofy:state_change': {
        const message =
            /** @type {{path: string, state: !cros.factory.TestState}} */ (
                untypedMessage);
        this.setTestState(message.path, message.state);
        break;
      }
      case 'goofy:init_test_ui': {
        const message =
            /** @type {{test: string, invocation: string}} */ (untypedMessage);
        const invocation =
            this.createInvocation(message.test, message.invocation);

        invocation.loaded.then(() => {
          const doc = goog.asserts.assert(invocation.iframe.contentDocument);
          this.updateCSSClassesInDocument(doc);
        });

        goog.events.listen(
            invocation.iframe.contentWindow, goog.events.EventType.KEYDOWN,
            this.keyListener.bind(this));
        break;
      }
      case 'goofy:set_html': {
        const message = /**
         * @type {{test: string, invocation: string, id: ?string,
         *     append: boolean, html: string, autoscroll: boolean}}
         */ (untypedMessage);
        const invocation = this.invocations.get(message.invocation);
        if (!invocation) {
          break;
        }

        invocation.loaded.then(() => {
          const document = invocation.iframe.contentDocument;
          const element =
              message.id ? document.getElementById(message.id) : document.body;
          if (!element) {
            return;
          }

          // Add some margin so that people don't need to scroll to the very
          // bottom to make autoscroll work.
          const scrollAtBottom =
              (element.scrollTop >=
               element.scrollHeight - element.clientHeight - 10);

          if (message.append) {
            const fragment = cros.factory.utils.createFragmentFromHTML(
                message.html, goog.asserts.assert(document));
            element.appendChild(fragment);
          } else {
            element.innerHTML = message.html;
          }

          if (message.autoscroll && scrollAtBottom) {
            element.scrollTop = element.scrollHeight - element.clientHeight;
          }
        });
        break;
      }
      case 'goofy:import_html': {
        const message = /**
         * @type {{test: string, invocation: string, url: string}}
         */ (untypedMessage);
        const invocation = this.invocations.get(message.invocation);
        if (invocation) {
          invocation.loaded = invocation.loaded.then(async () => {
            const doc = invocation.iframe.contentDocument;
            const response = await fetch(message.url);
            const html = await response.text();
            const fragment = cros.factory.utils.createFragmentFromHTML(
                html, goog.asserts.assert(doc));

            doc.head.appendChild(fragment);
          });
        }
        break;
      }
      case 'goofy:run_js': {
        const message = /**
         * @type {{test: string, invocation: string, args: !Object, js: string}}
         */ (untypedMessage);
        const invocation = this.invocations.get(message.invocation);
        if (invocation) {
          invocation.loaded.then(() => {
            // We need to evaluate the code in the context of the content
            // window, but we also need to give it a variable.  Stash it in the
            // window and load it directly in the eval command.
            invocation.iframe.contentWindow.__goofy_args = message.args;
            invocation.iframe.contentWindow.eval(
                `const args = window.__goofy_args; ${message.js}`);
            if (invocation) {
              delete invocation.iframe.contentWindow.__goofy_args;
            }
          });
        }
        break;
      }
      case 'goofy:extension_rpc': {
        const message = /**
         * @type {{is_response: boolean, name: string, args: !Object,
         *     rpc_id: string}}
         */ (untypedMessage);
        if (!message.is_response) {
          window.chrome.runtime.sendMessage(
              cros.factory.EXTENSION_ID,
              {name: message.name, args: message.args}, async (...args) => {
                // If an error occurs while connecting to the extension, this
                // function would be called without arguments. In this case we
                // should ignore this result.
                if (args.length === 1) {
                  // The web socket has size limit 65536 bytes. Thus we save
                  // a temporary file and then send the url back, instead of
                  // sending the base64-encoded string.
                  if (args[0]['save_file']) {
                    const path = await this.sendRpc('UploadTemporaryFile',
                                                    args[0].content);
                    args[0] = path;
                  }
                  this.sendEvent(messageType, {
                    name: message.name,
                    rpc_id: message.rpc_id,
                    is_response: true,
                    args: args[0]
                  });
                }
              });
        }
        break;
      }
      case 'goofy:destroy_test': {
        const message = /** @type {{invocation: string}} */ (untypedMessage);
        // We send destroy_test event only in the top-level invocation from
        // Goofy backend.
        cros.factory.logger.info(
            `Received destroy_test event for top-level invocation ${
                message.invocation}`);
        const invocation = this.invocations.get(message.invocation);
        if (invocation) {
          invocation.dispose();
        }
        break;
      }
      case 'goofy:pending_shutdown': {
        const message =
            /** @type {?cros.factory.PendingShutdownEvent} */ (untypedMessage);
        this.setPendingShutdown(message);
        break;
      }
      case 'goofy:update_notes': {
        this.sendRpc('DataShelfGetValue', 'factory_note', true)
            .then((/** !Array<!cros.factory.Note> */ notes) => {
              this.updateNote(notes);
            });
        break;
      }
      case 'goofy:diagnosis_tool:event': {
        const message = /** @type {!Object} */ (untypedMessage);
        this.diagnosisTool.handleBackendEvent(message);
        break;
      }
      case 'goofy:set_test_ui_layout': {
        const message =
            /** @type {{layout_type: string, layout_options: !Object}} */ (
                untypedMessage);
        this.setTestUILayout(message.layout_type, message.layout_options);
        break;
      }
    }
  }

  /**
   * Start the terminal session.
   */
  launchTerminal() {
    if (this.terminal_win) {
      this.terminal_win.style.display = '';
      document.getElementById('goofy-terminal').style.opacity = 1.0;
      return;
    }

    const mini = goog.dom.createDom('div', 'goofy-terminal-minimize');
    const close = goog.dom.createDom('div', 'goofy-terminal-close');
    const win = goog.dom.createDom(
        'div', {class: 'goofy-terminal-window', id: 'goofy-terminal-window'},
        goog.dom.createDom('div', 'goofy-terminal-title', 'Terminal'),
        goog.dom.createDom('div', 'goofy-terminal-control', mini, close));

    goog.events.listen(
        close, goog.events.EventType.MOUSEUP, this.closeTerminal.bind(this));
    goog.events.listen(
        mini, goog.events.EventType.MOUSEUP, this.hideTerminal.bind(this));
    document.body.appendChild(win);

    const ws_url = `ws://${window.location.host}/pty`;
    const sock = new WebSocket(ws_url);

    this.terminal_sock = sock;
    this.terminal_win = win;

    sock.onerror = (/** !Error */ e) => {
      goog.log.info(cros.factory.logger, 'socket error', e);
    };
    jQuery(win).draggable({
      handle: '.goofy-terminal-title',
      stop(/** ? */ event, /** {helper: jQuery.Type} */ ui) {
        // Remove the width and height set by draggable, so the size is same as
        // child size.
        ui.helper.css('width', '');
        ui.helper.css('height', '');
      }
    });
    sock.onopen = () => {
      const term =
          new Terminal({cols: 80, rows: 24, useStyle: true, screenKeys: true});
      term.open(win);
      term.on('data', (data) => {
        sock.send(data);
      });
      sock.onmessage = ({/** string */ data}) => {
        term.write(Base64.decode(data));
      };

      const $terminal = jQuery(term.element);
      const widthPerChar = term.element.clientWidth / term.cols;
      const heightPerChar = term.element.clientHeight / term.rows;

      $terminal.resizable({
        grid: [widthPerChar, heightPerChar],
        minWidth: 20 * widthPerChar,
        minHeight: 5 * heightPerChar,
        resize: (
            /** ? */ event,
            /** {size: {width: number, height: number}} */ ui) => {
          const newCols = Math.round(ui.size.width / widthPerChar);
          const newRows = Math.round(ui.size.height / heightPerChar);
          if (newCols !== term.cols || newRows !== term.rows) {
            term.resize(newCols, newRows);
            term.refresh(0, term.rows - 1);

            // Ghost uses the CONTROL_START and CONTROL_END to know the control
            // string.
            // format: CONTROL_START ControlString CONTROL_END
            const CONTROL_START = 128;
            const CONTROL_END = 129;
            const msg = {command: 'resize', params: [newRows, newCols]};
            // Send to ghost to set new size
            sock.send((new Uint8Array([CONTROL_START])).buffer);
            sock.send(JSON.stringify(msg));
            sock.send((new Uint8Array([CONTROL_END])).buffer);
          }
        }
      });
    };
    sock.onclose = () => {
      this.closeTerminal();
    };
  }

  /**
   * Close the terminal window.
   */
  closeTerminal() {
    if (this.terminal_win) {
      this.terminal_win.remove();
      this.terminal_win = null;
      this.terminal_sock.close();
      this.terminal_sock = null;
    }
  }

  /**
   * Hide the terminal window.
   */
  hideTerminal() {
    this.terminal_win.style.display = 'none';
    document.getElementById('goofy-terminal').style.opacity = 0.5;
  }

  /**
   * Setup the UI for plugin.
   * @param {!Array<!cros.factory.PluginFrontendConfig>} configs
   */
  setPluginUI(configs) {
    for (const {location, url} of configs) {
      const pluginArea =
          document.getElementById(`goofy-plugin-area-${location}`);
      const newPlugin = goog.dom.createDom('div', 'goofy-plugin');
      const iframe = goog.asserts.assertInstanceof(
          goog.dom.createDom(
              'iframe', {'class': 'goofy-plugin-iframe', 'src': url}),
          HTMLIFrameElement);
      pluginArea.appendChild(newPlugin);
      newPlugin.appendChild(iframe);
      iframe.contentWindow.plugin = new cros.factory.Plugin(this, newPlugin);
      // TODO(pihsun): Extract these exports to iframe to a function.
      iframe.contentWindow.cros = cros;
      iframe.contentWindow.goog = goog;
      iframe.contentWindow.goofy = this;
      iframe.contentWindow._ = _;
      iframe.onload = () => {
        this.updateCSSClassesInDocument(
            goog.asserts.assert(iframe.contentDocument));
      };
      iframe.contentWindow.addEventListener('focus', () => {
        this.focusInvocation();
      });
    }
    if (configs.some(({location}) => location === 'goofy-full')) {
      // We need to trigger a window resize event if there's a UI with full
      // width, so the top level splitpane would be sized properly.
      goog.events.fireListeners(
          window, goog.events.EventType.RESIZE, false, null);
    }
  }
};

/** @type {!goog.i18n.DateTimeFormat} */
cros.factory.Goofy.MDHMS_TIME_FORMAT =
    new goog.i18n.DateTimeFormat('MM/dd HH:mm:ss');

/** @type {!goog.i18n.DateTimeFormat} */
cros.factory.Goofy.HMS_TIME_FORMAT = new goog.i18n.DateTimeFormat('HH:mm:ss');

/** @type {!goog.i18n.DateTimeFormat} */
cros.factory.Goofy.FULL_TIME_FORMAT =
    new goog.i18n.DateTimeFormat('yyyy-MM-dd HH:mm:ss.SSS');

goog.events.listenOnce(window, goog.events.EventType.LOAD, () => {
  window.goofy = new cros.factory.Goofy();
  window.goofy.preInit();
});
