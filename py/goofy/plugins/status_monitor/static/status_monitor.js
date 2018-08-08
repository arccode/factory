// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const statusMonitor = {};

/**
 * Time interval for each status update checking.
 * @const
 * @type {number}
 */
statusMonitor.SYSTEM_STATUS_INTERVAL_MSEC = 5000;

/**
 * @typedef {{charge_manager: Object,
 *     battery: ?{charge_fraction: ?number, charge_state: ?string},
 *     fan_rpm: ?number, temperature: number, load_avg: Array<number>,
 *     cpu: ?Array<number>, ips: string, eth_on: boolean, wlan_on: boolean}}
 */
statusMonitor.SystemStatus;

/**
 * Labels for items in system info.
 * @type {Array<{key: string, label: !goog.html.SafeHtml,
 *     transform: ?function(?string): !goog.html.SafeHtml}>}
 */
statusMonitor.SYSTEM_INFO_LABELS = [
  {key: 'mlb_serial_number', label: _('MLB S/N')},
  {key: 'serial_number', label: _('S/N')}, {key: 'stage', label: _('Stage')},
  {key: 'ip', label: _('IP Address')},
  {key: 'test_image_version', label: _('Test Image')},
  {key: 'release_image_version', label: _('Release Image')},
  {key: 'firmware_version', label: _('Main Firmware')},
  {key: 'kernel_version', label: _('Kernel')},
  {key: 'architecture', label: _('Architecture')},
  {key: 'ec_version', label: _('EC')}, {key: 'pd_version', label: _('PD')},
  {key: 'root_device', label: _('Root Device')},
  {key: 'device_id', label: _('Device ID')}, {
    key: 'toolkit_version',
    label: _('Factory Toolkit Version'),
    transform: (/** ?string */ value) => {
      if (value == null) {
        return cros.factory.i18n.i18nLabel('(no update)');
      }
      return goog.html.SafeHtml.htmlEscape(value);
    }
  },
  {key: 'hwid_database_version', label: _('HWID Database Version')}
];

/** @type {!goog.html.SafeHtml} */
statusMonitor.UNKNOWN_LABEL = goog.html.SafeHtml.create(
    'span', {class: 'goofy-unknown'}, cros.factory.i18n.i18nLabel('Unknown'));

/**
 * Main status plugin object.
 */
statusMonitor.Status = class {
  /**
   * @param {cros.factory.Plugin} plugin
   */
  constructor(plugin) {
    /**
     * Tooltip for showing system information.
     */
    this.infoTooltip = goog.dom.createDom('div', 'info-tooltip');
    this.infoTooltip.innerText = 'Version information not yet available.';

    /**
     * Plugin object.
     * @type {cros.factory.Plugin}
     */
    this.plugin = plugin;

    /**
     * Last system info received.
     * @type {Object<string, *>}
     */
    this.systemInfo = {};
  }

  /**
   * Starts running the plugin.
   */
  start() {
    this.plugin.addPluginTooltip(
        document.getElementById('system-info-hover'), this.infoTooltip);

    this.initUI();

    window.setInterval(
        this.updateStatus.bind(this),
        statusMonitor.SYSTEM_STATUS_INTERVAL_MSEC);
    this.updateStatus();

    window.setInterval(this.updateTime.bind(this), 1000);
    this.updateTime();
  }

  /**
   * Initialize the UI.
   */
  initUI() {
    const container = document.getElementById('status-bar-left');
    for (const {key, label} of statusMonitor.SYSTEM_INFO_LABELS) {
      const div = goog.dom.createDom(
          'div', {'id': key, 'class': 'status-bar-section'}, [
            goog.dom.createDom(
                'div', 'status-bar-label',
                cros.factory.i18n.i18nLabelNode(label)),
            goog.dom.createDom('div', 'status-bar-value')
          ]);
      container.appendChild(div);
    }
  }

  /**
   * Updates the current time.
   */
  updateTime() {
    const element = this.infoTooltip.querySelector('#time');
    if (element) {
      element.innerText =
          new goog.date.DateTime().toUTCIsoString(true) + ' UTC';
    }
  }

  /**
   * Updates the tooltip and status-bar items.
   */
  updateTooltip() {
    const rows = [];
    for (const {key, label, transform} of statusMonitor.SYSTEM_INFO_LABELS) {
      const value = this.systemInfo[key];
      let html;
      if (transform) {
        html = transform(value);
      } else {
        html = value == null ? statusMonitor.UNKNOWN_LABEL : value;
      }
      html = goog.html.SafeHtml.htmlEscape(html);

      const element = document.getElementById(key);
      goog.dom.safe.setInnerHtml(
          element.getElementsByClassName('status-bar-value')[0], html);

      rows.push(goog.html.SafeHtml.create('tr', {}, [
        goog.html.SafeHtml.create(
            'th', {}, cros.factory.i18n.i18nLabel(label)),
        goog.html.SafeHtml.create('td', {}, html)
      ]));
    }
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create(
          'th', {}, cros.factory.i18n.i18nLabel('System time')),
      goog.html.SafeHtml.create('td', {id: 'time'})
    ]));

    const table = goog.html.SafeHtml.create('table', {id: 'system-info'}, rows);
    goog.dom.safe.setInnerHtml(this.infoTooltip, table);
    $(this.infoTooltip).find('th, td').css({
      'font-size': '0.75em',
      'text-align': 'left',
      'padding': '0 .1em 0 .1em',
      'white-space': 'nowrap'
    });
    $(this.infoTooltip).find('th').css({'padding-right': '1em'});

    this.updateTime();
  }

  /**
   * Update system status.
   */
  async updateStatus() {
    const /** ?Object<string, *> */ systemInfo = (await goofy.sendRpcToPlugin(
        'status_monitor.status_monitor', 'GetSystemInfo')) || {};
    const lastStatus = this.systemInfo;
    this.systemInfo = systemInfo;
    this.updateTooltip();

    const status =
        /** @type {!statusMonitor.SystemStatus} */ (systemInfo);

    const setValue = (/** string */ id, /** ?string */ value) => {
      const element = document.getElementById(id);
      element.classList.toggle('value-known', value != null);
      goog.dom.setTextContent(
          goog.dom.getElementByClass('value', element), value || '');
    };

    /**
     * @param {?statusMonitor.SystemStatus} oldStatus
     * @param {?statusMonitor.SystemStatus} newStatus
     * @return {boolean}
     */
    const canCalculateCpuStatus = (oldStatus, newStatus) => {
      return !!oldStatus && !!oldStatus['cpu'] && !!newStatus['cpu'];
    };

    if (canCalculateCpuStatus(lastStatus, status)) {
      const lastCpu = goog.math.sum.apply(this, lastStatus['cpu']);
      const currentCpu = goog.math.sum.apply(this, status['cpu']);
      const /** number */ lastIdle = lastStatus['cpu'][3];
      const /** number */ currentIdle = status['cpu'][3];
      const deltaIdle = currentIdle - lastIdle;
      const deltaTotal = currentCpu - lastCpu;
      setValue(
          'percent-cpu',
          statusMonitor.Status.PERCENT_CPU_FORMAT.format(
              (deltaTotal - deltaIdle) / deltaTotal));
    } else {
      setValue('percent-cpu', null);
    }

    const chargeIndicator = document.getElementById('battery-charge-indicator');
    let percent = null;
    let batteryChargeState = 'unknown';
    if (status.battery) {
      if (status.battery.charge_fraction != null) {
        percent = statusMonitor.Status.PERCENT_BATTERY_FORMAT.format(
            status.battery.charge_fraction);
      }
      if (goog.array.contains(
              ['IDLE', 'CHARGE', 'DISCHARGE'],
              status.battery.charge_state)) {
        batteryChargeState = status.battery.charge_state.toLowerCase();
      }
    }
    setValue('percent-battery', percent);
    chargeIndicator.className = 'battery-' + batteryChargeState;

    const /** ?number */ temperature = status['temperature'];
    const temp = temperature != null ? Math.round(temperature) + '°C' : null;
    setValue('temperature', temp);

    const eth_indicator = document.getElementById('eth-indicator');
    eth_indicator.classList.toggle('eth-enabled', status['eth_on']);
    const wlan_indicator = document.getElementById('wlan-indicator');
    wlan_indicator.classList.toggle('wlan-enabled', status['wlan_on']);
  }
};

/** @type {goog.i18n.NumberFormat} */
statusMonitor.Status.LOAD_AVERAGE_FORMAT = new goog.i18n.NumberFormat('0.00');

/** @type {goog.i18n.NumberFormat} */
statusMonitor.Status.PERCENT_CPU_FORMAT = new goog.i18n.NumberFormat('0.0%');

/** @type {goog.i18n.NumberFormat} */
statusMonitor.Status.PERCENT_BATTERY_FORMAT = new goog.i18n.NumberFormat('0%');

const statusPlugin = new statusMonitor.Status(plugin);
statusPlugin.start();
