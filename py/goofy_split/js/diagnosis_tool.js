// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.DiagnosisTool');
goog.provide('cros.factory.DiagnosisTool.FuncInfo');
goog.provide('cros.factory.DiagnosisTool.FuncInfo.Input');

goog.require('goog.array');
goog.require('goog.dom');
goog.require('goog.string');
goog.require('goog.ui.Button');
goog.require('goog.ui.Component');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.LabelInput');
goog.require('goog.ui.Prompt');
goog.require('goog.ui.Select');
goog.require('goog.ui.Slider');
goog.require('goog.ui.SplitPane');
goog.require('goog.ui.Tooltip');
goog.require('goog.ui.tree.TreeControl');


/**
 * @constructor
 * @param {cros.factory.Goofy} goofy
 */
cros.factory.DiagnosisTool = function(goofy) {
  this.goofy = goofy;

  /**
   * A dictionary to store each confirm dialog.  We need to store this
   * information because user can stop the function when it is showing a confirm
   * dialog.
   * @type {?Object}
   */
  this.confirmDialog_ = {};

  /**
   * The main window component of the diagnosis tool.  It will be initialized
   * in initWindow().
   * @type {?goog.ui.Component}
   */
  this.mainWindow_ = null;

  /**
   * The component of the tree view of the functions for user to select which
   * function to run.  It will be initialized in initWindowFuncMenu().
   * @type {?goog.ui.tree.TreeControl}
   */
  this.funcMenu_ = null;

  /**
   * An element to display the name of the current function.  It will be
   * initialized in initWindowRightUpperPart().
   * @type {?Element}
   */
  this.name_ = null;

  /**
   * A component to store each description of the functions and to display the
   * current one.  It will be initialized in initWindowRightUpperPart().
   * @type {?goog.ui.Component}
   */
  this.descriptions_ = null;

  /**
   * A component to store each input of the functions and to display the
   * current one.  It will be initialized in initWindowRightUpperPart().
   * @type {?goog.ui.Component}
   */
  this.inputs_ = null;

  /**
   * A button to start the current function.  It will be initialized in
   * initWindowRightUpperPart().
   * @type {?goog.ui.Button}
   */
  this.startButton_ = null;

  /**
   * A button to clear the output of the current function.  It will be
   * initialized in initWindowRightUpperPart().
   * @type {?goog.ui.Button}
   */
  this.clearButton_ = null;

  /**
   * A button to stop the current function.  It will be initialized in
   * initWindowRightUpperPart().
   * @type {?goog.ui.Button}
   */
  this.stopButton_ = null;

  /**
   * A component to store each output of the functions and to display the
   * current one.  It will be initialized in initWindowRightLowerPart().
   * @type {?goog.ui.Component}
   */
  this.outputs_ = null;

  /**
   * Stores all function's information.  It will be initialized in
   * initFuncMenuAndInfo().
   * @type {Object.<string, cros.factory.DiagnosisTool.FuncInfo>}
   */
  this.funcInfo_ = {};

  /**
   * Stores the current state.
   * @type {?Element}
   */
  this.currentState_ = null;

  /**
   * Stores the current function.
   * @type {?cros.factory.DiagnosisTool.FuncInfo}
   */
  this.currentFunc_ = null;

  this.initWindow();
};


/**
 * Width of the function menu of the diagnosis tool, as a fraction of the dialog
 * size.
 * @const
 * @type number
 */
cros.factory.DiagnosisTool.FUNC_MENU_WIDTH_FACTOR = 0.2;


/**
 * Height of the output console of the diagnosis tool, as a fraction of the
 * dialog size.
 * @const
 * @type number
 */
cros.factory.DiagnosisTool.OUTPUT_HEIGHT_FACTOR = 0.4;


/**
 * The ID property of the main window element.
 * @const
 * @type string
 */
cros.factory.DiagnosisTool.MAIN_WINDOW_ID = 'diagnosis-tool';


/**
 * Prefix string of the ID property of the element about states.
 * @const
 * @type string
 */
cros.factory.DiagnosisTool.COMMAND_STATE_ID_PREFIX = 'diagnosis-tool-state-';


/**
 * Enum the states in the Factory Diagnosis Tool.
 * @enum {string}
 */
cros.factory.DiagnosisTool.State = {
  RUNNING: 'running',
  DONE: 'done',
  FAILED: 'failed',
  STOPPING: 'stopping',
  STOPPED: 'stopped',
  NONE: 'none',  // If the function has not been run yet and it is runnable.
  NOT_APPLICABLE: 'not-applicable'  /* If the function is not runnable (which
                                     * may be just a group of other functions).
                                     */
};


/**
 * Gets the string (which is hashable) format of a list.
 */
cros.factory.DiagnosisTool.listToHashableObj = function(pathName) {
  var LIST_DELIMITER = '.delimiterrrr?';
  var s = '';
  for (var i = 0, iMax = pathName.length; i < iMax; ++i) {
    s += pathName[i] + LIST_DELIMITER;
  }
  return s;
};


/**
 * Gets the html tag id property for a specified state.
 * @param {string} state
 */
cros.factory.DiagnosisTool.getStateId = function(state) {
  return cros.factory.DiagnosisTool.COMMAND_STATE_ID_PREFIX + state;
};


/**
 * Creates the GUI of the factory diagnosis tool.
 *
 * Window structure: (Star means that it is a member of 'this')
 *   +- mainWindow* ----------------------------------------------------------+
 *   | +- funcMenu* ------+ || name: [funcName*]                              |
 *   | | System Utility   | || state: running/done/failed/... [stopButton*]   |
 *   | | Update Firmware  | || description:                                   |
 *   | | Logs             | || +- description* -----------------------------+ |
 *   | |   FW log         | || |                                            | |
 *   | |   View EC        | || |                                            | |
 *   | |   EC panic info  | || +--------------------------------------------+ |
 *   | | Reboot           | || input:                                         |
 *   | |   Warm reboot    | || +- input* -----------------------------------+ |
 *   | |   Cold EC reset  | || |                                            | |
 *   | |   Recovery mode  | || |                                            | |
 *   | | HWID             | || +--------------------------------------------+ |
 *   | |   Probe hardware | || [startButton*]                  [clearButton*] |
 *   | |                  | ||================================================|
 *   | |                  | || +- output* ----------------------------------+ |
 *   | |                  | || |                                            | |
 *   | |                  | || |                                            | |
 *   | +------------------+ || +--------------------------------------------+ |
 *   +------------------------------------------------------------------------+
 */
cros.factory.DiagnosisTool.prototype.initWindow = function() {
  // Setup main window.
  this.mainWindow_ = new goog.ui.Dialog();
  this.mainWindow_.setModal(false);
  this.mainWindow_.setTitle("Diagnosis Tool");
  this.mainWindow_.createDom();
  var viewportSize = goog.dom.getViewportSize(goog.dom.getWindow(document) ||
                                              window);
  var width = viewportSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
  var height = viewportSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;
  goog.style.setBorderBoxSize(this.mainWindow_.getContentElement(),
                              new goog.math.Size(width, height));
  goog.dom.setProperties(this.mainWindow_.getElement(),
                         {'id': cros.factory.DiagnosisTool.MAIN_WINDOW_ID});
  this.mainWindow_.setButtonSet(null);
  this.goofy.registerDialog(this.mainWindow_);
  this.mainWindow_.setDisposeOnHide(false);
  // Split the window into left/right pane.
  var horizontalSplitpane = new goog.ui.SplitPane(  /* Split the window */
      this.initWindowFuncMenu(),
      new goog.ui.Component(),
      goog.ui.SplitPane.Orientation.HORIZONTAL);
  var leftWidth = width * cros.factory.DiagnosisTool.FUNC_MENU_WIDTH_FACTOR;
  horizontalSplitpane.setInitialSize(leftWidth);
  this.mainWindow_.setVisible(true);  // Let the SplitPane know how large it is.
  this.mainWindow_.addChild(horizontalSplitpane, true);
  horizontalSplitpane.getChildAt(1).addChild(this.initWindowRightPart(), true);
  this.mainWindow_.setVisible(false);

  this.initFuncMenuAndInfo();
};


/**
 * Creates the components for the function menu.
 */
cros.factory.DiagnosisTool.prototype.initWindowFuncMenu = function() {
  this.funcMenu_ = new goog.ui.tree.TreeControl('Function Menu');
  this.funcMenu_.setShowRootNode(false);
  return this.funcMenu_;
};


/**
 * Creates the components at the right part of the window.
 */
cros.factory.DiagnosisTool.prototype.initWindowRightPart = function() {
  var verticalSplitpane = new goog.ui.SplitPane(
      this.initWindowRightUpperPart(),
      this.initWindowRightLowerPart(),
      goog.ui.SplitPane.Orientation.VERTICAL);
  var viewportSize = goog.dom.getViewportSize(goog.dom.getWindow(document) ||
                                              window);
  var height = viewportSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;
  var upSize = height * (1 - cros.factory.DiagnosisTool.OUTPUT_HEIGHT_FACTOR);
  verticalSplitpane.setInitialSize(upSize);
  return verticalSplitpane;
};


/**
 * Creates the components at the right upper part of the window.
 *
 * It includes name, state, description, input, etc.
 */
cros.factory.DiagnosisTool.prototype.initWindowRightUpperPart = function() {
  var addPromptRow = function(en, zh) {
    return goog.dom.createDom('div', {},
                              goog.dom.htmlToDocumentFragment(
                                  cros.factory.Label(en, zh)));
  };

  var nameRow = addPromptRow("Name:", "名称:");
  var name = goog.dom.createDom('span');
  goog.dom.append(nameRow, name);

  var stateRow = addPromptRow("State:", "状态:");
  for (var key in cros.factory.DiagnosisTool.State) {
    var value = cros.factory.DiagnosisTool.State[key];
    var stateId = cros.factory.DiagnosisTool.getStateId(value);
    goog.dom.append(stateRow, goog.dom.createDom('span', {"id": stateId}));
  }
  var stopButton = new goog.ui.Button('stop');
  stopButton.createDom();
  goog.dom.append(stateRow, stopButton.getElement());

  var descriptionPrompt = addPromptRow("Description:", '说明/描述:');
  var description = new goog.ui.Component();
  description.createDom();

  var inputPrompt = addPromptRow("Input:", '输入:');
  var input = new goog.ui.Component();
  input.createDom();

  var startButton = new goog.ui.Button('start');
  startButton.createDom();

  var clearButton = new goog.ui.Button('clear');
  clearButton.createDom();
  goog.dom.setProperties(clearButton.getElement(),
                         {"id": "diagnosis-tool-clear-button"})

  var all = new goog.ui.Component();
  all.createDom();
  goog.dom.append(/** @type {!Node} */(all.getElement()),
                  nameRow,
                  stateRow,
                  descriptionPrompt,
                  description.getElement(),
                  inputPrompt,
                  input.getElement(),
                  startButton.getElement(),
                  clearButton.getElement());
  this.mainWindow_.addChild(description, false);
  this.mainWindow_.addChild(input, false);
  this.mainWindow_.addChild(startButton, false);
  this.mainWindow_.addChild(clearButton, false);
  this.mainWindow_.addChild(stopButton, false);
  this.name_ = name;
  this.descriptions_ = description;
  this.inputs_ = input;
  this.startButton_ = startButton;
  this.clearButton_ = clearButton;
  this.stopButton_ = stopButton;
  return all;
};


/**
 * Creates the component for the output console.
 */
cros.factory.DiagnosisTool.prototype.initWindowRightLowerPart = function() {
  this.outputs_ = new goog.ui.Component();
  return this.outputs_;
};


/**
 * Initalizes the content of the function menu and the information of each
 * function in the factory diagnosis tool.
 */
cros.factory.DiagnosisTool.prototype.initFuncMenuAndInfo = function() {
  var rpcCallback = function(data) {
    var path = [];
    var that = this;
    var createFuncMenuAndInfo = function(tree, parent, list) {
      goog.array.extend(path, list[0]);
      var node = tree.createNode(goog.string.htmlEscape(list[0]));
      node.originalName = list[0];
      parent.add(node);
      if (list.length > 1) {
        var children = list[1];
        for (var i = 0, iMax = children.length; i < iMax; ++i) {
          createFuncMenuAndInfo(tree, node, children[i]);
        }
      }
      var newFunc = new cros.factory.DiagnosisTool.FuncInfo(
          path, node, that.descriptions_, that.inputs_, that.outputs_, that);
      var hashableObj = cros.factory.DiagnosisTool.listToHashableObj(path);
      that.funcInfo_[hashableObj] = newFunc;
      goog.array.removeAt(path, path.length - 1);
    }
    for (var i = 0, iMax = data.length; i < iMax; ++i) {
      createFuncMenuAndInfo(this.funcMenu_, this.funcMenu_, data[i]);
    }
    this.funcMenu_.expandAll();

    this.initState();
  };
  this.sendRpc('GetFuncMenu', [], goog.bind(rpcCallback, this));
};


/**
 * Initalizes the states of the factory diagnosis tool.
 */
cros.factory.DiagnosisTool.prototype.initState = function() {
  var setup = function(state, en, zh) {
    var id = cros.factory.DiagnosisTool.getStateId(state);
    goog.dom.getElement(id).innerHTML = cros.factory.Label(en, zh);
    goog.dom.getElement(id).style['display'] = 'none';
  };
  var macroState = cros.factory.DiagnosisTool.State;
  setup(macroState.RUNNING, 'Running', '执行中');
  setup(macroState.DONE, 'Done', '完成');
  setup(macroState.FAILED, 'Failed', '失败');
  setup(macroState.STOPPING, 'Stopping', '中止中');
  setup(macroState.STOPPED, 'Stopped', '已中止');
  setup(macroState.NONE, 'None', '无');
  setup(macroState.NOT_APPLICABLE, 'Not applicable', '不适用');
  this.currentState_ = goog.dom.getElement(
      cros.factory.DiagnosisTool.getStateId(
          cros.factory.DiagnosisTool.State.NONE));

  this.initEvents();
};


/**
 * Adds events to the factory diagnosis tool.
 */
cros.factory.DiagnosisTool.prototype.initEvents = function() {
  var addEventHandler = goog.bind(function(node, path) {
    var label = node.getLabelElement();
    var myPath = goog.array.clone(path);
    goog.array.extend(myPath, node.originalName);
    goog.events.listen(label, goog.events.EventType.CLICK,
                       function(event) {
                         this.userRequestLoadFunction(myPath);
                       }, false, this);
    var children = node.getChildren();
    for (var i = 0, iMax = children.length; i < iMax; ++i) {
      addEventHandler(children[i], myPath);
    }
  }, this);
  var children = this.funcMenu_.getChildren();
  for (var i = 0, iMax = children.length; i < iMax; ++i) {
    addEventHandler(children[i], []);
  }
  var action = goog.ui.Component.EventType.ACTION;
  goog.events.listen(this.mainWindow_, goog.ui.Component.EventType.HIDE,
                     function(event) {
                       this.userHideWindow();
                     }, false, this);
  goog.events.listen(this.startButton_, action,
                     function(event) {
                       this.userRequestStartFunction();
                     }, false, this);
  goog.events.listen(this.stopButton_, action,
                     function(event) {
                       this.userRequestStopFunction();
                     }, false, this);
  goog.events.listen(this.clearButton_, action,
                     function(event) {
                       this.userClearFunctionOutput();
                     }, false, this);
};


/**
 * Calls an RPC function using goofy.sendRpc() function
 * @param {string} method
 * @param {Object} args
 * @param {Object=} callback
 * @param {Object=} opt_errorCallback
 */
cros.factory.DiagnosisTool.prototype.sendRpc = function(
    method, args, callback, opt_errorCallback) {
  this.goofy.sendRpc('DiagnosisToolRpc', goog.array.concat([method], args),
                     callback, opt_errorCallback);
};


/**
 * Displays the factory diagnosis tool.
 */
cros.factory.DiagnosisTool.prototype.showWindow = function() {
  this.mainWindow_.setVisible(true);
  if (!this.currentFunc_) {  // First time to show window
    var children = this.funcMenu_.getChildren();
    if (children.length > 0) {
      // Automatically selects a function
      var child = children[0];
      for (var i in this.funcInfo_) {
        if (this.funcInfo_[i].node == child) {
          this.userRequestLoadFunction(this.funcInfo_[i].path);
          break;
        }
      }
    }
  }
  this.sendRpc('ShowWindow', [], null);
};


/**
 * Hides the factory diagnosis tool.
 */
cros.factory.DiagnosisTool.prototype.userHideWindow = function() {
  this.sendRpc('HideWindow', [], null);
};


/**
 * User requests to load another function but we need to confirm with backend
 * whether the request is allowed or not.
 * @param {Array.<string>} path path name
 */
cros.factory.DiagnosisTool.prototype.userRequestLoadFunction = function(path) {
  this.sendRpc('LoadFunction', [path, false],
               goog.bind(function(b) {
                 // If the return value of DiagnosisToolLoadFunction() in
                 // the backend is false, which means that the backend
                 // think that it will not load to another function
                 // immediately, we need to select back the function menu.
                 if (!b && this.currentFunc_ != null) {
                   // Selects to the original node so it will be looked
                   // like nothing happened.
                   var currNode = this.currentFunc_.node;
                   this.funcMenu_.setSelectedItem(currNode);
                 }
               }, this));
};


/**
 * User clicks start button to start a function.  It will collection the inputs
 * and then call backend to run the function.
 */
cros.factory.DiagnosisTool.prototype.userRequestStartFunction = function() {
  var inputs = {};
  for (var key in this.currentFunc_.inputs) {
    if (this.currentFunc_.inputs[key].getValue != undefined) {
      inputs[key] = this.currentFunc_.inputs[key].getValue();
    }
  }
  this.sendRpc("StartFunction", [this.currentFunc_.path, inputs]);
};


/**
 * User clicks clear button to clear the output of the current function.
 */
cros.factory.DiagnosisTool.prototype.userClearFunctionOutput = function() {
  if (this.currentFunc_) {
    this.currentFunc_.clearOutput();
  }
};


/**
 * User clicks stop button to stop a function.  It will just let the backend
 * know this event happened.
 */
cros.factory.DiagnosisTool.prototype.userRequestStopFunction = function() {
  this.sendRpc("StopFunction", [this.currentFunc_.path, false]);
};


/**
 * Loads another function.  This function will only be called by the backend.
 * @param {Array.<string>} path name
 */
cros.factory.DiagnosisTool.prototype.loadFunction = function(path) {
  if (this.currentFunc_) {
    // Let the original function be invisible.
    this.currentFunc_.setVisible(false);
  }
  var hashableObj = cros.factory.DiagnosisTool.listToHashableObj(path);
  var func = this.funcInfo_[hashableObj];
  if (!func.initialized) {
    this.sendRpc('InitFunction', [path], function() {
      func.initialized = true;
    });
  }
  this.currentFunc_ = func;
  this.currentFunc_.setVisible(true);
  this.funcMenu_.setSelectedItem(this.currentFunc_.node);
  this.name_.innerHTML = goog.string.htmlEscape(this.currentFunc_.name);
};


/**
 * Changes the state.
 * @param {string} state New state.
 */
cros.factory.DiagnosisTool.prototype.setState = function(state) {
  this.currentState_.style['display'] = 'none';
  var id = cros.factory.DiagnosisTool.getStateId(state);
  this.currentState_ = goog.dom.getElement(id);
  this.currentState_.style['display'] = 'inline';
  this.startButton_.setEnabled(
      state != cros.factory.DiagnosisTool.State.RUNNING &&
      state != cros.factory.DiagnosisTool.State.STOPPING &&
      state != cros.factory.DiagnosisTool.State.NOT_APPLICABLE);
  this.stopButton_.setEnabled(
      state == cros.factory.DiagnosisTool.State.RUNNING);
};


/**
 * Shows a confirm dialoag to confirm something.
 * @param {string} title Dialog window title.
 * @param {string} content Dialog window content.
 * @param {number|null} timeout Timeout.  Null means unlimited.
 * @param {Object.<string, null|function():*>} options Option buttons.
 * @param {string|null} defaultValue Default value.
 * @param {number} id ID of this confirm dialog.
 */
cros.factory.DiagnosisTool.prototype.confirmDialog = function(
    title, content, timeout, options, defaultValue, id) {
  var dialog = new goog.ui.Dialog();
  dialog.createDom();
  var dialogContent = /** @type {!Node} */(dialog.getContentElement());
  // Dialog setting
  dialog.setHasTitleCloseButton(false);
  dialog.setTitle(title);
  // Button setting
  var button = new goog.ui.Dialog.ButtonSet();
  var allOptions = {};
  for (var key in options) {
    button.set(key, key);
    allOptions[key] = options[key];
  }
  button.setDefault(defaultValue);
  dialog.setButtonSet(button);
  // Text setting
  var text = goog.dom.createDom('div');
  text.innerHTML = content;
  goog.dom.append(dialogContent, text);
  // Register and display
  this.goofy.registerDialog(dialog);
  dialog.setVisible(true);
  // Event handler
  var timer = null;
  var callCallback = goog.bind(function(key) {
    var callback = allOptions[key];
    if (callback != null) {
      this.sendRpc(callback[0], callback.slice(1, callback.length), null);
    }
    if (timer != null) {
      timer.stop();
    }
    this.confirmDialog_[id] = null;
  }, this);
  goog.events.listen(dialog, goog.ui.Dialog.EventType.SELECT, function(e) {
    callCallback(e.key);
  }, false, this);
  if (timeout && timeout > 0) {
    var timeoutText = goog.dom.createDom('span');
    var timeoutTime = goog.dom.createDom('span');
    timeoutText.innerHTML = cros.factory.Label('Time remaining: ',
                                               '剩余时间: ');
    timeoutTime.innerHTML = timeout;
    goog.dom.append(dialogContent, timeoutText, timeoutTime);
    timer = new goog.Timer(1000);  // Sets tick interval to 1000 ms (1s).
    timer.start();
    goog.events.listen(timer, goog.Timer.TICK, function(e) {
      --timeout;
      timeoutTime.innerHTML = timeout;
      if (timeout <= 0) {
        timer.stop();
        callCallback(defaultValue);
        dialog.setVisible(false);
      }
    }, false, this);
  }
  this.confirmDialog_[id] = {
    'dialog': dialog,
    'timer': timer
  };
};


/**
 * Stops the confirm dialog.
 * @param {number} id ID of the dialog window.
 */
cros.factory.DiagnosisTool.prototype.confirmDialogStop = function(id) {
  if (id in this.confirmDialog_ && this.confirmDialog_[id] != null) {
    this.confirmDialog_[id]['dialog'].setVisible(false);
    if (this.confirmDialog_[id]['timer'] != null) {
      this.confirmDialog_[id]['timer'].stop();
    }
    this.confirmDialog_[id] = null;
  }
};


/**
 * Handles the event coming from the backend.
 * @param {Object} message event
 */
cros.factory.DiagnosisTool.prototype.handleBackendEvent = function(message) {
  var SUB_TYPE = 'sub_type';
  if (message[SUB_TYPE] == 'loadFunction') {
    this.loadFunction(message['path']);
  } else if (message[SUB_TYPE] == 'confirmDialog') {
    this.confirmDialog(message['title'],
                       message['content'],
                       message['timeout'],
                       message['options'],
                       message['default_value'],
                       message['id']);
  } else if (message[SUB_TYPE] == 'confirmDialogStop') {
    this.confirmDialogStop(message['id']);
  } else if (message[SUB_TYPE] == 'setState') {
    this.setState(message['state']);
  } else if (message[SUB_TYPE] == 'setFunctionDescription') {
    this.currentFunc_.setFunctionDescription(message['description']);
  } else if (message[SUB_TYPE] == 'addFunctionInputs') {
    this.currentFunc_.addInputs(message['inputs']);
  } else if (message[SUB_TYPE] == 'delFunctionInputs') {
    this.currentFunc_.delInputs(message['inputs']);
  } else if (message[SUB_TYPE] == 'addFunctionOutputLines') {
    this.currentFunc_.addOutputLines(message['text'], message['escape']);
  } else if (message[SUB_TYPE] == 'setFunctionOutputLine') {
    this.currentFunc_.setOutputLine(message['text'],
                                    message['escape'],
                                    message['line']);
  } else if (message[SUB_TYPE] == 'clearFunctionOutput') {
    this.currentFunc_.clearOutput();
  }
};


/**
 * A class for storing information of a function.
 * @constructor
 * @param {Array.<string>} path Path name.
 * @param {goog.ui.tree.TreeNode} node Tree node.
 * @param {goog.ui.Component} descriptions Component to place my descrption
 *     of this function.
 * @param {goog.ui.Component} inputs Component to place my inputs of this
 *     function.
 * @param {goog.ui.Component} outputs Component to place my output of this
 *     function.
 * @param {cros.factory.DiagnosisTool} diagnosisTool
 */
cros.factory.DiagnosisTool.FuncInfo = function(
    path, node, descriptions, inputs, outputs, diagnosisTool) {
  this.path = goog.array.clone(path);
  this.name = path[path.length - 1];
  this.node = node;
  this.initialized = false;
  this.inputs = {};
  this.descriptionComponent_ = new goog.ui.Component();
  this.inputComponent_ = new goog.ui.Component();
  this.outputComponent_ = new goog.ui.Component();
  this.diagnosisTool_ = diagnosisTool;
  descriptions.addChild(this.descriptionComponent_, true);
  inputs.addChild(this.inputComponent_, true);
  outputs.addChild(this.outputComponent_, true);
  this.setVisible(false);
};


/**
 * Types of the inputs of the functions in factory diagnosis tool.
 * @enum {string}
 */
cros.factory.DiagnosisTool.FuncInfo.InputType = {
  NUMBER: 'number',
  SLIDER: 'slider',
  CHOICES: 'choices',
  BOOL: 'bool',
  FILE: 'file',
  STRING: 'string',
  BUTTON: 'button'
};


/**
 * Adds a prompt and help tooltip to a dom object.
 *
 * @param {string} prefix
 * @param {string} suffix
 * @param {string} helpText
 * @param {Object} input an DOM element
 * @return {goog.ui.Component}
 */
cros.factory.DiagnosisTool.FuncInfo.addInputPrompt = function(
    prefix, suffix, helpText, input) {
  var ret = new goog.ui.Component();
  ret.createDom();
  goog.dom.append(/** @type {!Node} */(ret.getElement()),
                  goog.dom.htmlToDocumentFragment(prefix),
                  input,
                  goog.dom.htmlToDocumentFragment(suffix));
  var tp = new goog.ui.Tooltip(ret.getElement(), helpText);
  return ret;
};


/**
 * Sets whether this function be visible or not.
 * @param {boolean} b
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.setVisible = function(b) {
  if (b) {
    this.descriptionComponent_.getElement().style['display'] = 'block';
    this.inputComponent_.getElement().style['display'] = 'block';
    this.outputComponent_.getElement().style['display'] = 'block';
  } else {
    this.descriptionComponent_.getElement().style['display'] = 'none';
    this.inputComponent_.getElement().style['display'] = 'none';
    this.outputComponent_.getElement().style['display'] = 'none';
  }
};


/**
 * Sets the description of the function.
 * @param {string} desc Description.
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.setFunctionDescription = function(
    desc) {
  this.descriptionComponent_.getElement().innerHTML = desc;
};


/**
 * Adds some inputs.
 * @param {Array.<Object>} inputs An array contain the inputs to be added.
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addInputs = function(inputs) {
  for (var i = 0, iMax = inputs.length; i < iMax; ++i) {
    var input = inputs[i];
    var varId = input['var_id'];
    var type = input['type'];
    var prpt = input['prompt'];
    var help = input['help'];
    var ret;
    var remember = true;
    if (varId in this.inputs && this.inputs[varId] != null) {
      this.delInputs([varId]);
    }
    if (type == cros.factory.DiagnosisTool.FuncInfo.InputType.NUMBER) {
      ret = this.addInputNumber(prpt, help,
                                input['value'],
                                input['min'], input['max'], input['step'],
                                input['unit']);
    } else if (type == cros.factory.DiagnosisTool.FuncInfo.InputType.SLIDER) {
      ret = this.addInputSlider(prpt, help,
                                input['value'],
                                input['min'], input['max'], input['step'],
                                input['round'], input['unit']);
    } else if (type == cros.factory.DiagnosisTool.FuncInfo.InputType.CHOICES) {
      ret = this.addInputChoices(prpt, help, input['value'], input['choices']);
    } else if (type == cros.factory.DiagnosisTool.FuncInfo.InputType.BOOL) {
      ret = this.addInputBool(prpt, help, input['value']);
    } else if (type == cros.factory.DiagnosisTool.FuncInfo.InputType.FILE) {
      ret = this.addInputFile(prpt, help,
                              input['pattern'], input['file_type']);
    } else if (type == cros.factory.DiagnosisTool.FuncInfo.InputType.STRING) {
      ret = this.addInputString(prpt, help, input['value'], input['hint']);
    } else if (type == cros.factory.DiagnosisTool.FuncInfo.InputType.BUTTON) {
      ret = this.addInputButton(prpt, help, input['arguments']);
      remember = false;
    }
    if (remember) {
      this.inputs[varId] = ret;
    }
  }
};


/**
 * Removes some inputs.
 * @param {Array.<string>} inputs An array contains the name of the inputs
 *     which need to be removed.
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.delInputs = function(inputs) {
  for (var i = 0, iMax = inputs.length; i < iMax; ++i) {
    var name = inputs[i];
    if (!(name in this.inputs) || this.inputs[name] == null) {
      continue;
    }
    this.inputComponent_.removeChild(this.inputs[name].component, true);
    this.inputs[name] = null;
  }
};


/**
 * Adds a input with type 'number' to the function.
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {number} value Default value.
 * @param {number} min Minimal acceptable value.
 * @param {number} max Maximal acceptable value.
 * @param {number} step Minimal acceptable step.
 * @param {string} unit
 * @return {cros.factory.DiagnosisTool.FuncInfo.Input}
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addInputNumber = function(
    prpt, help, value, min, max, step, unit) {
  var input = goog.dom.createDom('input', {
    "type": "number",
    "min": String(min),
    "max": String(max),
    "step": String(step),
    "value": String(value)});
  var promptText = prpt + '[' + min + '~' + max + ']';
  var box = cros.factory.DiagnosisTool.FuncInfo.addInputPrompt(
      promptText, unit, help, input);
  this.inputComponent_.addChild(box, true);
  return new cros.factory.DiagnosisTool.FuncInfo.Input(
      function() {
        var val = Number(input.value);
        if (val < min) val = min;
        if (max < val) val = max;
        return val;
      },
      box);
};


/**
 * Adds a input with type "slider" to the function.
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {number} value Default value.
 * @param {number} min Minimum number.
 * @param {number} max Maximum number.
 * @param {number} step Step number.
 * @param {number} round Round for display.
 * @param {string} unit Unit.
 * @return {cros.factory.DiagnosisTool.FuncInfo.Input}
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addInputSlider = function(
    prpt, help, value, min, max, step, round, unit) {
  var slider = new goog.ui.Slider();
  slider.setOrientation(goog.ui.Slider.Orientation.HORIZONTAL);
  slider.setMinimum(min);
  slider.setMaximum(max);
  slider.setStep(step);
  if (value != null) {
    slider.setValue(value);
  }
  slider.render();
  goog.dom.append(/** @type {!Node} */(slider.getElement()),
                  goog.dom.createDom('div', {
                    "class": "diagnosis-tool-input-slider-horizontal-line"}));
  var text = goog.dom.createDom('span');
  var all = goog.dom.createDom('div', {"class": "diagnosis-tool-input-div"},
                               slider.getElement(), text);
  var box = cros.factory.DiagnosisTool.FuncInfo.addInputPrompt(
      prpt, unit, help, all);
  this.inputComponent_.addChild(box, true);
  goog.events.listen(slider, goog.ui.Component.EventType.CHANGE,
                     function(event) {
                       var val = Number(slider.getValue());
                       text.innerHTML = val.toFixed(round);
                     }, false, {'slider': slider, 'text': text});
  return new cros.factory.DiagnosisTool.FuncInfo.Input(
      function() { return slider.getValue().toFixed(round); }, box);
};


/**
 * Adds a input with type 'choices' to the function.
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {string} value Default value.
 * @param {Array.<string>} choices Allowed choices.
 * @return {cros.factory.DiagnosisTool.FuncInfo.Input}
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addInputChoices = function(
    prpt, help, value, choices) {
  var select = new goog.ui.Select(value);
  for (var i = 0, iMax = choices.length; i < iMax; ++i) {
    var item = new goog.ui.MenuItem(choices[i]);
    select.addItem(item);
  }
  select.setValue(value);
  select.render();
  var box = cros.factory.DiagnosisTool.FuncInfo.addInputPrompt(
      prpt, '', help, select.getElement());
  this.inputComponent_.addChild(box, true);
  return new cros.factory.DiagnosisTool.FuncInfo.Input(
      function() { return select.getValue(); }, box);
};


/**
 * Adds a input with type 'boolean' to the function.
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {boolean|null} value Default value.
 * @return {cros.factory.DiagnosisTool.FuncInfo.Input}
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addInputBool = function(
    prpt, help, value) {
  var checkBox = new goog.ui.Checkbox();
  checkBox.render();
  checkBox.setChecked(value);
  var box = cros.factory.DiagnosisTool.FuncInfo.addInputPrompt(
      '', prpt, help, checkBox.getElement());
  this.inputComponent_.addChild(box, true);
  return new cros.factory.DiagnosisTool.FuncInfo.Input(
      function() { return (checkBox.getChecked() ? "true" : "false"); }, box);
};


/**
 * Adds a input with type "file" to the function.
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {string} pattern A regular expression pattern.
 * @param {string} type File type.
 * @return {cros.factory.DiagnosisTool.FuncInfo.Input}
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addInputFile = function(
    prpt, help, pattern, type) {
  var button = new goog.ui.Button("Select...");
  var label = goog.dom.createDom('span');
  var all = goog.dom.createElement('div');
  goog.dom.setProperties(all, {"class": "diagnosis-tool-input-div"});
  button.render();
  goog.dom.append(all, button.getElement(), label);
  var box = cros.factory.DiagnosisTool.FuncInfo.addInputPrompt(
      prpt, '', help, all);
  this.inputComponent_.addChild(box, true);
  // TODO(yhong): use a real file manager.
  // -- File manager (start) --
  // Here it just calls a very simple file manager which only contains a prompt
  // dialog for user to input a path name.
  var filename = '';
  var p = new goog.ui.Prompt('Simple File Manager', 'Input a path name',
                             function(str) {
                               label.innerHTML = goog.string.htmlEscape(str);
                               filename = str;
                             });
  goog.events.listen(button, goog.ui.Component.EventType.ACTION, function(e) {
    p.setVisible(true);
  }, false, this);
  // -- File manager (end) --
  return new cros.factory.DiagnosisTool.FuncInfo.Input(
      function() { return filename; }, box);
};


/**
 * Adds a input with type "string" to the function.
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {string|null} value Default value.
 * @param {string} hint Hint.
 * @return {cros.factory.DiagnosisTool.FuncInfo.Input}
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addInputString = function(
    prpt, help, value, hint) {
  var input = new goog.ui.LabelInput(hint);
  input.render();
  if (value != null) {
    input.setValue(value);
  }
  var box = cros.factory.DiagnosisTool.FuncInfo.addInputPrompt(
      prpt, '', help, input.getElement());
  this.inputComponent_.addChild(box, true);
  return new cros.factory.DiagnosisTool.FuncInfo.Input(
      function() { return input.getValue(); }, box);
};


/**
 * Adds a input with type "button" to the function.
 *
 * The usage of a button is different from other types.  When the backend runs a
 * function, which mainly be a series of linux commands, it will consider values
 * of normal inputs (not includes button because it don't have a value) as a
 * input of the commands.
 *
 * On the other hand, the backend will receive their values if and only if the
 * user clicks the "start" button to run a function, but in this case, function
 * 'DiagnosisToolPressInputButton()' in the backend will be called immediately
 * when the button be clicked.
 *
 * @param {string} caption Button's caption.
 * @param {string} help Help text.
 * @param {Array} args
 * @return {cros.factory.DiagnosisTool.FuncInfo.Input}
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addInputButton = function(
    caption, help, args) {
  var button = new goog.ui.Button(caption);
  button.setTooltip(help);
  this.inputComponent_.addChild(button, true);
  goog.events.listen(button, goog.ui.Component.EventType.ACTION,
                     function(event) {
                       var allArgs = goog.array.concat([this.path], args);
                       this.diagnosisTool_.sendRpc('PressInputButton',
                                                   allArgs, null);
                     }, false, this);
  return new cros.factory.DiagnosisTool.FuncInfo.Input(function() {}, button);
};


/**
 * Adds lines to the output.
 *
 * @param {string} text
 * @param {boolean} esc Do htmlEscape() or not.
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.addOutputLines = function(
    text, esc) {
  var lines = text.split("\n");
  for (var i = 0, iMax = lines.length; i < iMax; ++i) {
    var line = new goog.ui.Component();
    this.outputComponent_.addChild(line, true);
    if (esc) {
      var escLine = goog.string.htmlEscape(lines[i], true);
      line.getElement().innerHTML = escLine;
    } else {
      line.getElement().innerHTML = lines[i];
    }
  }
};


/**
 * Changes a line in the output.
 *
 * @param {string} text
 * @param {boolean} esc Do htmlEscape() or not.
 * @param {number} num Line number.
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.setOutputLine = function(
    text, esc, num) {
  var lineCount = this.outputComponent_.getChildCount();
  var index = (num >= 0 ? num : lineCount + num);
  if (0 <= index && index < lineCount) {
    var line = this.outputComponent_.getChildAt(index);
    if (esc) {
      line.getElement().innerHTML = goog.string.htmlEscape(text);
    } else {
      line.getElement().innerHTML = text;
    }
  }
};


/**
 * Clears the output.
 */
cros.factory.DiagnosisTool.FuncInfo.prototype.clearOutput = function() {
  this.outputComponent_.removeChildren(true);
};


/**
 * An simple object for storing information about a input.
 * @constructor
 * @param {function():*} getValue A function to get the value of this input.
 * @param {goog.ui.Component} comp The component of this input.
 */
cros.factory.DiagnosisTool.FuncInfo.Input = function(getValue, comp) {
  this.getValue = getValue;
  this.component = comp;
};
