// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.DiagnosisTool');
goog.provide('cros.factory.DiagnosisTool.Inputs');
goog.provide('cros.factory.DiagnosisTool.Inputs.InputField');

goog.require('cros.factory.i18n');
goog.require('goog.array');
goog.require('goog.dom');
goog.require('goog.string');
goog.require('goog.ui.Button');
goog.require('goog.ui.Checkbox');
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
   * Stores each confirm dialog.  We need to store this data because user can
   * stop the task when it is showing a confirm dialog.
   * @type {?Object}
   * @private
   */
  this.confirmDialog_ = {};

  /**
   * The main window component of the diagnosis tool.  It will be initialized
   * in initWindow().
   * @type {?goog.ui.Component}
   * @private
   */
  this.mainWindow_ = null;

  /**
   * The component of the tree view of the tasks for user to select which task
   * to run.  It will be initialized in initWindowTaskMenu().
   * @type {?goog.ui.tree.TreeControl}
   * @private
   */
  this.menuComponent_ = null;

  /**
   * Stores the name of the current task.  It will be initialized in
   * initWindowRightUpperPart().
   * @type {?Element}
   * @private
   */
  this.nameElement_ = null;

  /**
   * Stores the element of state. It will be initialized in
   * initWindowRightUpperPart().
   * @type {?goog.ui.Component}
   * @private
   */
  this.stateRowComponent_ = null;

  /**
   * Stores the description of the current task.  It will be initialized in
   * initWindowRightUpperPart().
   * @type {?Element}
   * @private
   */
  this.descriptionElement_ = null;

  /**
   * Stores the prompt string of the descriptionElement.  It will be initialized
   * in initWindowRightUpperPart().
   * @type {?Element}
   * @private
   */
  this.descriptionPromptElement_ = null;

  /**
   * Stores the input fields of the current task.  It will be initialized
   * in initWindowRightUpperPart().
   * @type {?goog.ui.Component}
   * @private
   */
  this.inputsComponent_ = null;

  /**
   * Stores the prompt string of the inputsComponent_.  It will be initialized
   * in initWindowRightUpperPart().
   * @type {?Element}
   * @private
   */
  this.inputsPromptElement_ = null;

  /**
   * Stores the output text of the tasks.  It will be initialized in
   * initWindowRightLowerPart().
   * @type {?Element}
   * @private
   */
  this.outputElement_ = null;

  /**
   * A button to start the current task.  It will be initialized in
   * initWindowRightUpperPart().
   * @type {?goog.ui.Button}
   * @private
   */
  this.startButton_ = null;

  /**
   * A button to clear the output of the current task.  It will be initialized
   * in initWindowRightUpperPart().
   * @type {?goog.ui.Button}
   * @private
   */
  this.clearButton_ = null;

  /**
   * A button to stop the current task.  It will be initialized in
   * initWindowRightUpperPart().
   * @type {?goog.ui.Button}
   * @private
   */
  this.stopButton_ = null;

  /**
   * Stores the current state.
   * @type {?Element}
   * @private
   */
  this.currentState_ = null;

  /**
   * Stores the id of the current task.
   * @type {?string}
   * @private
   */
  this.currentTaskId_ = null;

  /**
   * Stores the current menu node.
   * @type {?goog.ui.tree.TreeNode}
   * @private
   */
  this.currentMenuNode_ = null;

  /**
   * Stores the menu nodes with keys as the task id.
   * @type {?Object<string, goog.ui.tree.TreeNode>}
   * @private
   */
  this.menuNodes_ = {};

  /**
   * Stores all the input fields.  It will be initialized in
   * initWindowRightUpperPart().
   * @type {?cros.factory.DiagnosisTool.Inputs}
   * @private
   */
  this.inputs_ = null;

  /**
   * Whether the compontents has been initialized or not.
   * @type {boolean}
   * @private
   */
  this.initialized_ = false;
};


/**
 * Width of the menu of the diagnosis tool, as a fraction of the dialog size.
 * @const
 * @type {number}
 */
cros.factory.DiagnosisTool.FUNC_MENU_WIDTH_FACTOR = 0.35;


/**
 * Height of the output console of the diagnosis tool, as a fraction of the
 * dialog size.
 * @const
 * @type {number}
 */
cros.factory.DiagnosisTool.OUTPUT_HEIGHT_FACTOR = 0.4;


/**
 * The ID property of the main window element.
 * @const
 * @type {string}
 */
cros.factory.DiagnosisTool.MAIN_WINDOW_ID = 'diagnosis-tool';


/**
 * Prefix string of the ID property of the element about states.
 * @const
 * @type {string}
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
  IDLE: 'idle',  // If the task has not been run yet and it is runnable.
  NOT_APPLICABLE: 'not-applicable' /* If the task is not runnable (which may
                                    * be just a group of other tasks).
                                    */
};


/**
 * Gets the html tag id property for a specified state.
 * @param {string} state
 * @return {string}
 */
cros.factory.DiagnosisTool.getStateId = function(state) {
  return cros.factory.DiagnosisTool.COMMAND_STATE_ID_PREFIX + state;
};


/**
 * Calls an RPC function using goofy.sendRpc() function.
 * @param {string} method
 * @param {!Array<?>} args
 * @param {function(this:cros.factory.Goofy, ?)=} callback
 * @param {function(this:cros.factory.Goofy, ?)=} opt_errorCallback
 */
cros.factory.DiagnosisTool.prototype.sendRpc = function(
    method, args, callback, opt_errorCallback) {
  this.goofy.sendRpc('DiagnosisToolRpc', method, ...args)
      .then(
          callback ? callback.bind(this.goofy) : null,
          opt_errorCallback ? opt_errorCallback.bind(this.goofy) : null);
};


/**
 * Creates the GUI of the factory diagnosis tool.
 *
 * Window structure: (Star means that it is a member of 'this')
 *   +- mainWindow* ----------------------------------------------------------+
 *   | +- menu * ---------+ || name: [name*]                                  |
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
  this.mainWindow_ =
      this.goofy.createSimpleDialog('Diagnosis Tool', goog.html.SafeHtml.EMPTY);
  goog.dom.setProperties(
      this.mainWindow_.getElement(),
      {'id': cros.factory.DiagnosisTool.MAIN_WINDOW_ID});
  this.mainWindow_.setButtonSet(null);
  this.mainWindow_.setDisposeOnHide(false);
  // Split the window into left/right pane.
  var horizontalSplitpane = new goog.ui.SplitPane(
      this.initWindowMenu(), new goog.ui.Component(),
      goog.ui.SplitPane.Orientation.HORIZONTAL);
  this.mainWindow_.setVisible(true);  // Let the SplitPane know how large it is.
  var leftWidth = this.mainWindow_.getElement().offsetWidth *
      cros.factory.DiagnosisTool.FUNC_MENU_WIDTH_FACTOR;
  horizontalSplitpane.setInitialSize(leftWidth);
  this.mainWindow_.addChild(horizontalSplitpane, true);
  var rightPart = this.initWindowRightPart();
  horizontalSplitpane.getChildAt(1).addChild(rightPart, true);
  var classNames = [
    'goog-splitpane-first-container', 'goog-splitpane-second-container',
    'goog-splitpane-handle'
  ];
  for (var className of classNames) {
    var element = rightPart.getElement().getElementsByClassName(className)[0];
    element.style['width'] = '100%';
  }
  this.mainWindow_.setVisible(false);
};


/**
 * Creates the components for the menu.
 * @return {!goog.ui.tree.TreeControl}
 */
cros.factory.DiagnosisTool.prototype.initWindowMenu = function() {
  this.menuComponent_ = new goog.ui.tree.TreeControl('');
  this.menuComponent_.setShowRootNode(false);
  return this.menuComponent_;
};


/**
 * Creates the components at the right part of the window.
 * @return {!goog.ui.SplitPane}
 */
cros.factory.DiagnosisTool.prototype.initWindowRightPart = function() {
  var verticalSplitpane = new goog.ui.SplitPane(
      this.initWindowRightUpperPart(), this.initWindowRightLowerPart(),
      goog.ui.SplitPane.Orientation.VERTICAL);
  var upSize = this.mainWindow_.getElement().offsetHeight *
      (1 - cros.factory.DiagnosisTool.OUTPUT_HEIGHT_FACTOR);
  verticalSplitpane.setInitialSize(upSize);
  return verticalSplitpane;
};


/**
 * Creates the components at the right upper part of the window.
 *
 * It includes name, state, description, input, etc.
 * @return {!goog.ui.Component}
 */
cros.factory.DiagnosisTool.prototype.initWindowRightUpperPart = function() {
  var all = new goog.ui.Component();
  all.createDom();
  var all_element = /** @type {!Node} */ (all.getElement());

  this.nameElement_ = goog.dom.createDom('div', 'name');
  goog.dom.appendChild(all_element, this.nameElement_);

  this.stateRowComponent_ = new goog.ui.Component();
  all.addChild(this.stateRowComponent_, true);
  var row_element = /** @type {!Node} */ (this.stateRowComponent_.getElement());
  goog.dom.appendChild(row_element, cros.factory.i18n.i18nLabelNode('State:'));
  for (var key in cros.factory.DiagnosisTool.State) {
    var value = cros.factory.DiagnosisTool.State[key];
    var stateId = cros.factory.DiagnosisTool.getStateId(value);
    var stateElement = goog.dom.createDom('span', {'id': stateId}, value);
    goog.dom.appendChild(row_element, stateElement);
    stateElement.style['display'] = 'none';
  }

  this.descriptionPromptElement_ = goog.dom.createDom(
      'div', {}, cros.factory.i18n.i18nLabelNode('Description:'));
  this.descriptionElement_ =
      goog.dom.createDom('div', 'description');
  goog.dom.appendChild(all_element, this.descriptionPromptElement_);
  goog.dom.appendChild(all_element, this.descriptionElement_);

  this.inputsPromptElement_ =
      goog.dom.createDom('div', {}, cros.factory.i18n.i18nLabelNode('Input:'));
  this.inputsComponent_ = new goog.ui.Component();
  goog.dom.appendChild(all_element, this.inputsPromptElement_);
  all.addChild(this.inputsComponent_, true);
  goog.dom.setProperties(
      this.inputsComponent_.getElement(), {'class': 'inputs'});
  this.inputs_ = new cros.factory.DiagnosisTool.Inputs(this.inputsComponent_);

  this.startButton_ = new goog.ui.Button('start');
  all.addChild(this.startButton_, true);
  this.stopButton_ = new goog.ui.Button('stop');
  all.addChild(this.stopButton_, true);

  this.clearButton_ = new goog.ui.Button('clear');
  all.addChild(this.clearButton_, true);
  goog.dom.setProperties(
      this.clearButton_.getElement(), {'id': 'diagnosis-tool-clear-button'});

  goog.events.listen(
      this.startButton_, goog.ui.Component.EventType.ACTION, function(event) {
        this.userRequestStartTask();
      }, false, this);
  goog.events.listen(
      this.stopButton_, goog.ui.Component.EventType.ACTION, function(event) {
        this.userRequestStopTask();
      }, false, this);
  goog.events.listen(
      this.clearButton_, goog.ui.Component.EventType.ACTION, function(event) {
        this.userClearOutput();
      }, false, this);
  return all;
};


/**
 * Creates the component for the output console.
 * @return {!goog.ui.Component}
 */
cros.factory.DiagnosisTool.prototype.initWindowRightLowerPart = function() {
  var outputComponent = new goog.ui.Component();
  outputComponent.createDom();
  this.outputElement_ = outputComponent.getElement();
  goog.dom.setProperties(this.outputElement_, {'class': 'output'});
  return outputComponent;
};


/**
 * Displays the factory diagnosis tool.
 */
cros.factory.DiagnosisTool.prototype.showWindow = function() {
  if (!this.initialized_) {
    this.initWindow();
    this.setState(cros.factory.DiagnosisTool.State.NOT_APPLICABLE);
    this.setDescription('');
    this.setInputs([]);
    this.sendRpc('ShowWindow', []);
    this.initialized_ = true;
  }
  this.mainWindow_.setVisible(true);
};


/**
 * Sets the menu.
 * @param {!Array<!Object<string, string>>} config
 */
cros.factory.DiagnosisTool.prototype.setMenu = function(config) {
  var createMenu = goog.bind(function(tree, nodeParent, config) {
    var node = tree.createNode(goog.string.htmlEscape(config['name']));
    nodeParent.add(node);
    this.menuNodes_[config['task_id']] = node;
    if ('member' in config) {
      var children_config = config['member'];
      for (var i = 0, iMax = children_config.length; i < iMax; ++i) {
        createMenu(tree, node, children_config[i]);
      }
    }
  }, this);
  for (var i = 0, iMax = config.length; i < iMax; ++i) {
    createMenu(this.menuComponent_, this.menuComponent_, config[i]);
  }
  this.menuComponent_.expandAll();
  for (var id in this.menuNodes_) {
    goog.events.listen(
        this.menuNodes_[id].getLabelElement(),
        goog.events.EventType.CLICK, function(id) {
          return function(evt) {
            this.userRequestLoadTask(id);
          };
        }(id), false, this);
  }
};


/**
 * User clicks start button to start a task.  It will collect the inputs and
 * then call backend to run the task.
 */
cros.factory.DiagnosisTool.prototype.userRequestStartTask = function() {
  this.sendRpc('StartTask', [this.currentTaskId_, this.inputs_.getValues()]);
};


/**
 * User clicks stop button to stop a task.  It will just let the backend know
 * this event happened.
 */
cros.factory.DiagnosisTool.prototype.userRequestStopTask = function() {
  this.sendRpc('StopTask', [this.currentTaskId_]);
};


/**
 * User clicks clear button to clear the output of the current task.
 */
cros.factory.DiagnosisTool.prototype.userClearOutput = function() {
  this.clearOutput();
};


/**
 * User requests to load another task but we need to confirm with backend
 * whether the request is allowed or not.
 * @param {string} id Identity of the task.
 */
cros.factory.DiagnosisTool.prototype.userRequestLoadTask = function(id) {
  this.sendRpc('LoadTask', [id], goog.bind(function(b) {
    // If the return value of DiagnosisToolLoadTask() in
    // the backend is false, which means that the backend
    // thinks that it will not load another task immediately,
    // we need to switch back to the task menu.
    if (!b) {
      // Selects to the original node so it will be looked
      // like nothing happened.
      this.menuComponent_.setSelectedItem(this.currentMenuNode_);
    }
  }, this));
};


/**
 * Loads another task.  This function will only be called by the backend.
 * @param {string} id Identity of the task.
 */
cros.factory.DiagnosisTool.prototype.loadTask = function(id) {
  this.currentTaskId_ = id;
  this.currentMenuNode_ = this.menuNodes_[id];
  this.menuComponent_.setSelectedItem(this.currentMenuNode_);
  this.sendRpc('InitTask', [id]);
};


/**
 * Shows a confirm dialoag to confirm something.
 * @param {number} id ID of this confirm dialog.
 * @param {string} title Dialog window title.
 * @param {string} content Dialog window content.
 * @param {?number} timeout Timeout.  Null means unlimited.
 * @param {!Array<string>} options Options.
 * @param {?string} defaultOption Default option.
 */
cros.factory.DiagnosisTool.prototype.confirmDialog = function(
    id, title, content, timeout, options, defaultOption) {
  var dialog = new goog.ui.Dialog();
  dialog.createDom();
  var dialogContent = /** @type {!Element} */ (dialog.getContentElement());
  // Dialog setting
  dialog.setHasTitleCloseButton(false);
  dialog.setTitle(title);
  // Button setting
  var button = new goog.ui.Dialog.ButtonSet();
  for (var i = 0, iMax = options.length; i < iMax; ++i) {
    button.set(options[i], options[i]);
  }
  button.setDefault(defaultOption);
  dialog.setButtonSet(button);
  // Content text setting
  goog.dom.append(dialogContent, goog.dom.createDom('div', {}, content));
  // Register and display
  this.goofy.registerDialog(dialog);
  dialog.setVisible(true);
  // Event handler
  var timer = null;
  var callback = goog.bind(function(key) {
    if (timer != null) {
      timer.stop();
    }
    this.sendRpc('ConfirmSelected', [id, key]);
    this.confirmDialog_[id] = null;
  }, this);
  goog.events.listen(dialog, goog.ui.Dialog.EventType.SELECT, function(e) {
    callback(e.key);
  }, false, this);
  if (timeout) {
    var timeoutText = cros.factory.i18n.i18nLabelNode('Time remaining: ');
    var timeoutTime = goog.dom.createDom('span');
    timeoutTime.innerHTML = timeout;
    goog.dom.append(dialogContent, timeoutText, timeoutTime);
    timer = new goog.Timer(1000);  // Sets tick interval to 1000 ms (1s).
    timer.start();
    goog.events.listen(timer, goog.Timer.TICK, function(e) {
      --timeout;
      timeoutTime.innerHTML = timeout;
      if (timeout <= 0) {
        callback(defaultOption);
        dialog.setVisible(false);
      }
    }, false, this);
  }
  this.confirmDialog_[id] = {'dialog': dialog, 'timer': timer};
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
 * Sets the name of the current task.
 * @param {string} name Task name.
 */
cros.factory.DiagnosisTool.prototype.setName = function(name) {
  this.nameElement_.innerHTML = goog.string.htmlEscape(name);
};


/**
 * Changes the state.
 * @param {string} state New state.
 */
cros.factory.DiagnosisTool.prototype.setState = function(state) {
  if (this.currentState_ != null) {
    this.currentState_.style['display'] = 'none';
  }
  var id = cros.factory.DiagnosisTool.getStateId(state);
  this.currentState_ = goog.dom.getElement(id);
  this.currentState_.style['display'] = 'inline';
  if (state == cros.factory.DiagnosisTool.State.NOT_APPLICABLE) {
    this.stateRowComponent_.getElement().style['display'] = 'none';
    this.startButton_.getElement().style['display'] = 'none';
  } else {
    this.stateRowComponent_.getElement().style['display'] = 'block';
    this.startButton_.getElement().style['display'] = 'block';
  }
  this.startButton_.setVisible(
      state != cros.factory.DiagnosisTool.State.RUNNING &&
          state != cros.factory.DiagnosisTool.State.STOPPING &&
          state != cros.factory.DiagnosisTool.State.NOT_APPLICABLE,
      true);
  this.stopButton_.setVisible(
      state == cros.factory.DiagnosisTool.State.RUNNING, true);
};


/**
 * Sets the description of the task.
 * @param {string} desc Description.
 */
cros.factory.DiagnosisTool.prototype.setDescription = function(desc) {
  this.descriptionElement_.innerHTML = desc;
  if (desc == '') {
    this.descriptionPromptElement_.style['display'] = 'none';
    this.descriptionElement_.style['display'] = 'none';
  } else {
    this.descriptionPromptElement_.style['display'] = 'block';
    this.descriptionElement_.style['display'] = 'block';
  }
};


/**
 * Sets the input fields.
 * @param {!Array<Object>} inputs
 */
cros.factory.DiagnosisTool.prototype.setInputs = function(inputs) {
  var has_inputs = (this.inputs_.setInputs(inputs) > 0);
  if (has_inputs) {
    this.inputsPromptElement_.style['display'] = 'block';
    this.inputsComponent_.getElement().style['display'] = 'block';
  } else {
    this.inputsPromptElement_.style['display'] = 'none';
    this.inputsComponent_.getElement().style['display'] = 'none';
  }
};


/**
 * Appends text to the console output.
 * @param {string} text Text.
 */
cros.factory.DiagnosisTool.prototype.appendOutput = function(text) {
  var lines = text.split('\n');
  for (var i = 0, iMax = lines.length; i < iMax; ++i) {
    var line = goog.dom.createDom('div', {}, lines[i]);
    goog.dom.appendChild(this.outputElement_, line);
    if (i + 1 < iMax) {
      goog.dom.appendChild(this.outputElement_, goog.dom.createDom('br'));
    }
  }
};

/**
 * Clears the output of the current task.
 */
cros.factory.DiagnosisTool.prototype.clearOutput = function() {
  this.outputElement_.innerHTML = '';
};


/**
 * Handles the event coming from the backend.
 * @param {!Object} message event
 */
cros.factory.DiagnosisTool.prototype.handleBackendEvent = function(message) {
  var BACKEND_EVENT = 'sub_type';
  if (message[BACKEND_EVENT] == 'appendOutput') {
    this.appendOutput(message['text']);

  } else if (message[BACKEND_EVENT] == 'clearOutput') {
    this.clearOutput();

  } else if (message[BACKEND_EVENT] == 'confirmDialog') {
    this.confirmDialog(
        message['id'], message['title'], message['content'], message['timeout'],
        message['options'], message['default_option']);

  } else if (message[BACKEND_EVENT] == 'confirmDialogStop') {
    this.confirmDialogStop(message['id']);

  } else if (message[BACKEND_EVENT] == 'loadTask') {
    this.loadTask(message['task_id']);

  } else if (message[BACKEND_EVENT] == 'setDescription') {
    this.setDescription(message['description']);

  } else if (message[BACKEND_EVENT] == 'setInputs') {
    this.setInputs(message['inputs']);

  } else if (message[BACKEND_EVENT] == 'setMenu') {
    this.setMenu(message['menu']);

  } else if (message[BACKEND_EVENT] == 'setName') {
    this.setName(message['name']);

  } else if (message[BACKEND_EVENT] == 'setState') {
    this.setState(message['state']);
  }
};


/**
 * A class to handle all input fields.
 * @constructor
 * @param {goog.ui.Component} comp The component to display each input fields.
 */
cros.factory.DiagnosisTool.Inputs = function(comp) {
  /**
   * The component to display the input fields.
   * @type {goog.ui.Component}
   * @private
   */
  this.component_ = comp;

  /**
   * Stores all the input fields.
   * @private
   */
  this.fields_ = {};
};


/**
 * Types of the inputs of the tasks in factory diagnosis tool.
 * @enum {string}
 */
cros.factory.DiagnosisTool.Inputs.InputType = {
  NUMBER: 'number',
  SLIDER: 'slider',
  CHOICES: 'choices',
  BOOL: 'bool',
  FILE: 'file',
  STRING: 'string'
};


/**
 * Adds a prompt and help tooltip to a dom object.
 *
 * @param {string} prefix
 * @param {string} suffix
 * @param {string} helpText
 * @param {Node} input an DOM element
 * @return {goog.ui.Component}
 */
cros.factory.DiagnosisTool.Inputs.addFieldPrompt = function(
    prefix, suffix, helpText, input) {
  var ret = new goog.ui.Component();
  ret.createDom();
  goog.dom.append(
      /** @type {!Element} */ (ret.getElement()), prefix, input, suffix);
  if (helpText.length > 0) {
    var tp = new goog.ui.Tooltip(ret.getElement(), helpText);
  }
  return ret;
};


/**
 * Gets all the value of the fields.
 * @return {!Object<string, string>}
 */
cros.factory.DiagnosisTool.Inputs.prototype.getValues = function() {
  var ret = {};
  for (var key in this.fields_) {
    var value = this.fields_[key].getValue();
    if (value != null) {
      ret[key] = value;
    }
  }
  return ret;
};


/**
 * Sets the input fields.
 * @param {Array<Object>} inputs An array contain the inputs to be added.
 * @return {number} Number of the input fields was added.
 */
cros.factory.DiagnosisTool.Inputs.prototype.setInputs = function(inputs) {
  this.component_.removeChildren(true);
  this.fields_ = {};
  for (var i = 0, iMax = inputs.length; i < iMax; ++i) {
    var input = inputs[i];
    var varId = input['var_id'];
    var type = input['type'];
    var prpt = input['prompt'];
    var help = input['help'];
    var ret;
    if (type == cros.factory.DiagnosisTool.Inputs.InputType.NUMBER) {
      ret = this.addNumberField(
          prpt, help, input['value'], input['min'], input['max'], input['step'],
          input['round'], input['unit']);
    } else if (type == cros.factory.DiagnosisTool.Inputs.InputType.SLIDER) {
      ret = this.addSliderField(
          prpt, help, input['value'], input['min'], input['max'], input['step'],
          input['round'], input['unit']);
    } else if (type == cros.factory.DiagnosisTool.Inputs.InputType.CHOICES) {
      ret = this.addChoicesField(prpt, help, input['value'], input['choices']);
    } else if (type == cros.factory.DiagnosisTool.Inputs.InputType.BOOL) {
      ret = this.addBoolField(
          prpt, help, input['value'], input['enable_list'],
          input['disable_list']);
    } else if (type == cros.factory.DiagnosisTool.Inputs.InputType.FILE) {
      ret = this.addFileField(prpt, help, input['pattern'], input['file_type']);
    } else if (type == cros.factory.DiagnosisTool.Inputs.InputType.STRING) {
      ret = this.addStringField(prpt, help, input['value'], input['hint']);
    }
    this.fields_[varId] = ret;
  }
  var count = 0;
  for (var key in this.fields_) {
    var field = this.fields_[key];
    if (field.onChange) {
      field.onChange();
    }
    ++count;
  }
  return count;
};


/**
 * Adds a input field with type "number".
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {number} value Default value.
 * @param {number} min Minimum number.
 * @param {number} max Maximum number.
 * @param {number} step Step number.
 * @param {number} round Number of decimal places.
 * @param {string} unit Unit.
 * @return {!cros.factory.DiagnosisTool.Inputs.InputField}
 */
cros.factory.DiagnosisTool.Inputs.prototype.addNumberField = function(
    prpt, help, value, min, max, step, round, unit) {
  var input = goog.dom.createDom('input', {
    'type': 'number',
    'min': String(min),
    'max': String(max),
    'step': String(step),
    'value': String(value)
  });
  var promptText = prpt + '[' + min + '~' + max + ']: ';
  var box = cros.factory.DiagnosisTool.Inputs.addFieldPrompt(
      promptText, unit, help, input);
  this.component_.addChild(box, true);
  return new cros.factory.DiagnosisTool.Inputs.InputField(
      function() {
        if (input['disabled'] == true) {
          return null;
        }
        var val = Number(input.value);
        if (val < min)
          val = min;
        if (max < val)
          val = max;
        return val.toFixed(round);
      },
      function(b) {
        input['disabled'] = b;
      },
      null, box);
};


/**
 * Adds a field with type "slider".
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {number} value Default value.
 * @param {number} min Minimum number.
 * @param {number} max Maximum number.
 * @param {number} step Step number.
 * @param {number} round Number of decimal places.
 * @param {string} unit Unit.
 * @return {!cros.factory.DiagnosisTool.Inputs.InputField}
 */
cros.factory.DiagnosisTool.Inputs.prototype.addSliderField = function(
    prpt, help, value, min, max, step, round, unit) {
  var slider = new goog.ui.Slider();
  slider.setOrientation(goog.ui.Slider.Orientation.HORIZONTAL);
  slider.setMinimum(min);
  slider.setMaximum(max);
  slider.setStep(step);
  slider.setValue(value);
  slider.render();
  var sliderClassName = 'input-slider-horizontal-line';
  goog.dom.append(
      /** @type {!Element} */ (slider.getElement()),
      goog.dom.createDom('div', sliderClassName));
  var text = goog.dom.createDom('span');
  var all = goog.dom.createDom('div', 'input-div', slider.getElement(), text);
  var box =
      cros.factory.DiagnosisTool.Inputs.addFieldPrompt(prpt, unit, help, all);
  this.component_.addChild(box, true);
  goog.events.listen(
      slider, goog.ui.Component.EventType.CHANGE, function(event) {
        var val = Number(this.slider.getValue());
        this.text.innerHTML = val.toFixed(round);
      }, false, {'slider': slider, 'text': text});
  goog.events.dispatchEvent(slider, goog.ui.Component.EventType.CHANGE);
  var enabled = true;
  return new cros.factory.DiagnosisTool.Inputs.InputField(
      function() {
        return enabled ? slider.getValue().toFixed(round) : null;
      },
      function(b) {
        enabled = b;
        slider.setEnabled(b);
      },
      null, box);
};


/**
 * Adds a field with type "choices".
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {string} value Default value.
 * @param {Array<string>} choices Allowed choices.
 * @return {!cros.factory.DiagnosisTool.Inputs.InputField}
 */
cros.factory.DiagnosisTool.Inputs.prototype.addChoicesField = function(
    prpt, help, value, choices) {
  var select = new goog.ui.Select(value);
  for (var i = 0, iMax = choices.length; i < iMax; ++i) {
    var item = new goog.ui.MenuItem(choices[i]);
    select.addItem(item);
  }
  select.setValue(value);
  select.render();
  var dropButton = select.getElement().getElementsByClassName(
      'goog-inline-block goog-menu-button-dropdown')[0];
  dropButton.innerHTML = ' ▼';
  var box = cros.factory.DiagnosisTool.Inputs.addFieldPrompt(
      prpt, '', help, select.getElement());
  this.component_.addChild(box, true);
  var enabled = true;
  return new cros.factory.DiagnosisTool.Inputs.InputField(
      function() {
        return enabled ? select.getValue() : null;
      },
      function(b) {
        enabled = b;
        select.setEnabled(b);
      },
      null, box);
};


/**
 * Adds a field with type "boolean".
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {?boolean} value Default value.
 * @param {Array<number>} enable_list Which input should be enabled when true.
 * @param {Array<number>} disable_list Which input should be disable when true.
 * @return {!cros.factory.DiagnosisTool.Inputs.InputField}
 */
cros.factory.DiagnosisTool.Inputs.prototype.addBoolField = function(
    prpt, help, value, enable_list, disable_list) {
  var checkBox = new goog.ui.Checkbox();
  checkBox.render();
  checkBox.setChecked(value);
  var box = cros.factory.DiagnosisTool.Inputs.addFieldPrompt(
      '', prpt, help, checkBox.getElement());
  var that = this;
  var onChange = function() {
    var checked = checkBox.getChecked();
    for (var i = 0, iMax = enable_list.length; i < iMax; ++i) {
      if (that.fields_[enable_list[i]].setEnabled) {
        that.fields_[enable_list[i]].setEnabled(checked);
      }
    }
    for (var i = 0, iMax = disable_list.length; i < iMax; ++i) {
      if (that.fields_[disable_list[i]].setEnabled) {
        that.fields_[disable_list[i]].setEnabled(!checked);
      }
    }
  };
  goog.events.listen(
      checkBox, goog.ui.Component.EventType.CHANGE, function(event) {
        onChange();
      }, false, this);
  this.component_.addChild(box, true);
  var enabled = true;
  return new cros.factory.DiagnosisTool.Inputs.InputField(
      function() {
        if (enabled == false) {
          return null;
        }
        return checkBox.getChecked() ? 'true' : 'false';
      },
      function(b) {
        enabled = b;
        checkBox.setEnabled(b);
      },
      onChange, box);
};


/**
 * Adds a field with type "file".
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {string} pattern A regular expression pattern.
 * @param {string} type File type.
 * @return {!cros.factory.DiagnosisTool.Inputs.InputField}
 */
cros.factory.DiagnosisTool.Inputs.prototype.addFileField = function(
    prpt, help, pattern, type) {
  var button = new goog.ui.Button('Select...');
  var label = goog.dom.createDom('span');
  var all = goog.dom.createElement('div');
  goog.dom.setProperties(all, {'class': 'input-div'});
  button.render();
  goog.dom.append(all, button.getElement(), label);
  var box =
      cros.factory.DiagnosisTool.Inputs.addFieldPrompt(prpt, '', help, all);
  this.component_.addChild(box, true);
  // TODO(yhong): use a real file manager.
  // -- File manager (start) --
  // Here it just calls a very simple file manager which only contains a prompt
  // dialog for user to input a path name.
  var filename = '';
  var p = new goog.ui.Prompt(
      'Simple File Manager', 'Input a path name', function(str) {
        label.innerHTML = goog.string.htmlEscape(str);
        filename = str;
      });
  goog.events.listen(button, goog.ui.Component.EventType.ACTION, function(e) {
    p.setVisible(true);
  }, false, this);
  // -- File manager (end) --
  var enabled = true;
  return new cros.factory.DiagnosisTool.Inputs.InputField(
      function() {
        return enabled ? filename : null;
      },
      function(b) {
        enabled = b;
        button.setEnabled(b);
      },
      null, box);
};


/**
 * Adds a input field with type "string".
 *
 * @param {string} prpt Prompt string.
 * @param {string} help Help text.
 * @param {string} value Default value.
 * @param {string} hint Hint.
 * @return {!cros.factory.DiagnosisTool.Inputs.InputField}
 */
cros.factory.DiagnosisTool.Inputs.prototype.addStringField = function(
    prpt, help, value, hint) {
  var field = new goog.ui.LabelInput(hint);
  field.render();
  field.setValue(value);
  var box = cros.factory.DiagnosisTool.Inputs.addFieldPrompt(
      prpt, '', help, field.getElement());
  this.component_.addChild(box, true);
  var enabled = true;
  return new cros.factory.DiagnosisTool.Inputs.InputField(
      function() {
        return enabled ? field.getValue() : null;
      },
      function(b) {
        enabled = b;
        field.setEnabled(b);
      },
      null, box);
};


/**
 * An simple object for storing information about a input field.
 * @constructor
 * @param {?function():*} getValue Gets the value of this field.
 * @param {?function(boolean):*} setEnabled Sets enabled of this field.
 * @param {?function():*} onChange A function which will be called after the
 *     value be changed.
 * @param {goog.ui.Component} comp The component of this field.
 */
cros.factory.DiagnosisTool.Inputs.InputField = function(
    getValue, setEnabled, onChange, comp) {
  this.getValue = getValue;
  this.setEnabled = setEnabled;
  this.onChange = onChange;
  this.component = comp;
};
