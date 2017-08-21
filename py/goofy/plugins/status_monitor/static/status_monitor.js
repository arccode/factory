// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var status_monitor = {};

/**
 * Time interval for each status update checking.
 * @const
 * @type {number}
 */
status_monitor.SYSTEM_STATUS_INTERVAL_MSEC = 5000;

/**
 * @typedef {{charge_manager: Object,
 *     battery: ?{charge_fraction: ?number, charge_state: ?string},
 *     fan_rpm: ?number, temperature: number, load_avg: Array<number>,
 *     cpu: ?Array<number>, ips: string, eth_on: boolean, wlan_on: boolean}}
 */
status_monitor.SystemStatus;

/**
 * Labels for items in system info.
 * @type {Array<{key: string, label: !goog.html.SafeHtml,
 *     transform: ?function(?string): !goog.html.SafeHtml}>}
 */
status_monitor.SYSTEM_INFO_LABELS = [
  {
    key: 'mlb_serial_number',
    label: cros.factory.i18n.i18nLabel('MLB Serial Number')
  },
  {key: 'serial_number', label: cros.factory.i18n.i18nLabel('Serial Number')},
  {key: 'stage', label: cros.factory.i18n.i18nLabel('Stage')},
  {
    key: 'factory_image_version',
    label: cros.factory.i18n.i18nLabel('Factory Image Version')
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
  {key: 'pd_version', label: cros.factory.i18n.i18nLabel('PD')},
  {
    key: 'firmware_version',
    label: cros.factory.i18n.i18nLabel('Main Firmware')
  },
  {key: 'root_device', label: cros.factory.i18n.i18nLabel('Root Device')},
  {
    key: 'toolkit_version',
    label: cros.factory.i18n.i18nLabel('Factory Toolkit Version'),
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
status_monitor.UNKNOWN_LABEL = goog.html.SafeHtml.create(
    'span', {class: 'goofy-unknown'}, cros.factory.i18n.i18nLabel('Unknown'));

/**
 * Main status plugin object.
 *
 * @constructor
 * @param {cros.factory.Plugin} plugin
 */
status_monitor.Status = function(plugin) {

  /**
   * @type {?SystemStatus}
   */
  this.lastStatus = null;

  /**
   * Tooltip for showing system information.
   */
  this.infoTooltip = goog.dom.createDom('div', 'info-tooltip');
  this.infoTooltip.innerHTML = 'Version information not yet available.';

  /**
   * Plugin object.
   * @type {cros.factory.Plugin}
   */
  this.plugin = plugin;

  /**
   * Last system info received.
   * @type {Object<string, string>}
   */
  this.systemInfo = {};
};

/**
 * Starts running the plugin.
 */
status_monitor.Status.prototype.start = function() {
  this.plugin.addPluginTooltip(
      document.getElementById('system-info-hover'),
      this.infoTooltip);

  window.setInterval(
      goog.bind(this.updateStatus, this),
      status_monitor.SYSTEM_STATUS_INTERVAL_MSEC);
  this.updateStatus();

  var timer = new goog.Timer(1000);
  goog.events.listen(
      timer, goog.Timer.TICK, this.updateTime, false, this);
  timer.dispatchTick();
  timer.start();
};

/**
 * Updates the current time.
 */
status_monitor.Status.prototype.updateTime = function() {
  var element = $(this.plugin.dom).find('#time').get(0);
  if (element) {
    element.innerHTML = new goog.date.DateTime().toUTCIsoString(true) + ' UTC';
  }
};

/**
 * Updates the system info tooltip.
 * @param {Object<string, string>} systemInfo
 */
status_monitor.Status.prototype.setSystemInfo = function(systemInfo) {
  this.systemInfo = systemInfo || {};
  var rows = [];
  goog.array.forEach(status_monitor.SYSTEM_INFO_LABELS, function(item) {
    var value = this.systemInfo[item.key];
    var html;
    if (item.transform) {
      html = item.transform(value);
    } else {
      html = value == undefined ? status_monitor.UNKNOWN_LABEL : value;
    }
    rows.push(goog.html.SafeHtml.create('tr', {}, [
      goog.html.SafeHtml.create('th', {}, item.label),
      goog.html.SafeHtml.create('td', {}, html)
    ]));
  }, this);
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('Host Based')),
    goog.html.SafeHtml.create('td', {}, '1')
  ]));
  rows.push(goog.html.SafeHtml.create('tr', {}, [
    goog.html.SafeHtml.create(
        'th', {}, cros.factory.i18n.i18nLabel('System time')),
    goog.html.SafeHtml.create('td', {id: 'time'})
  ]));

  var table =
      goog.html.SafeHtml.create('table', {id: 'system-info'}, rows);
  goog.dom.safe.setInnerHtml(this.infoTooltip, table);
  $(this.infoTooltip).find('th, td').css({
      'font-size': '75%',
      'text-align': 'left',
      'padding': '0 .1em 0 .1em',
      'white-space': 'nowrap'
  });
  $(this.infoTooltip).find('th').css({
      'padding-right': '1em'
  });

  this.updateTime();

  if (this.systemInfo['update_toolkit_version']) {
    console.log('yes');
    $('#update-available-indicator').css({display: 'block'});
  } else {
    $('#update-available-indicator').css({display: 'none'});
  }
  $(this.plugin.dom).height($('body').height());
};

/** @type {goog.i18n.NumberFormat} */
status_monitor.Status.LOAD_AVERAGE_FORMAT = new goog.i18n.NumberFormat('0.00');

/** @type {goog.i18n.NumberFormat} */
status_monitor.Status.PERCENT_CPU_FORMAT = new goog.i18n.NumberFormat('0.0%');

/** @type {goog.i18n.NumberFormat} */
status_monitor.Status.PERCENT_BATTERY_FORMAT = new goog.i18n.NumberFormat('0%');

/**
 * Update system status.
 */
status_monitor.Status.prototype.updateStatus = function() {
  goofy.sendRpcToPlugin(
      'status_monitor.status_monitor',
      'GetSystemInfo', [],
      goog.bind(function(/** SystemInfo*/ systemInfo) {
        var status = systemInfo || {};
        Object.assign(this.systemInfo, status)
        this.setSystemInfo(this.systemInfo);

        function setValue(/** string */ id, /** ?string */ value) {
          var element = document.getElementById(id);
          goog.dom.classlist.enable(
              element, 'value-known', value != null);
          goog.dom.setTextContent(
              goog.dom.getElementByClass('value', element), value || '');
        }

        /**
         * @param {?status_monitor.SystemStatus} oldStatus
         * @param {?status_monitor.SystemStatus} newStatus
         * @return {boolean}
         */
        function canCalculateCpuStatus(oldStatus, newStatus) {
          return !!oldStatus && !!oldStatus['cpu'] && !!newStatus['cpu'];
        }

        setValue(
            'load-average', status['load_avg'] ?
                status_monitor.Status.LOAD_AVERAGE_FORMAT.format(
                    status['load_avg'][0]) :
                null);

        if (canCalculateCpuStatus(this.lastStatus, status)) {
          var lastCpu = goog.math.sum.apply(
              this, this.lastStatus['cpu']);
          var currentCpu = goog.math.sum.apply(this, status['cpu']);
          var /** number */ lastIdle = this.lastStatus['cpu'][3];
          var /** number */ currentIdle = status['cpu'][3];
          var deltaIdle = currentIdle - lastIdle;
          var deltaTotal = currentCpu - lastCpu;
          setValue(
              'percent-cpu',
              status_monitor.Status.PERCENT_CPU_FORMAT.format(
                  (deltaTotal - deltaIdle) / deltaTotal));
        } else {
          setValue('percent-cpu', null);
        }

        var chargeIndicator =
            document.getElementById('battery-charge-indicator');
        var percent = null;
        var batteryChargeState = 'unknown';
        if (status.battery) {
          if (status.battery.charge_fraction != null) {
            percent = status_monitor.Status.PERCENT_BATTERY_FORMAT.format(
                status.battery.charge_fraction);
          }
          if (goog.array.contains(
                  ['Full', 'Charging', 'Discharging'],
                  status.battery.charge_state)) {
            batteryChargeState = status.battery.charge_state.toLowerCase();
          }
        }
        setValue('percent-battery', percent);
        goog.dom.classlist.set(
            chargeIndicator, 'battery-' + batteryChargeState);

        var /** ?number */ temperature = status['temperature'];
        var temp = null;
        if (temperature != null) {
          temp = Math.round(temperature) + '°C';
        }
        setValue('temperature', temp);

        var eth_indicator = document.getElementById('eth-indicator');
        goog.dom.classlist.enable(
            eth_indicator, 'eth-enabled', status['eth_on']);
        var wlan_indicator = document.getElementById('wlan-indicator');
        goog.dom.classlist.enable(
            wlan_indicator, 'wlan-enabled', status['wlan_on']);

        this.lastStatus = status;
      }, this));
};

$(function() {
  var statusPlugin = new status_monitor.Status(plugin);
  statusPlugin.start();
});
