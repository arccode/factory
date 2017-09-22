// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

class StationSetup {
  constructor() {
    this.keys = [];
    this.properties = {};
    this.keyDesc = {};
  }
  static callRpc(funcName, ...args) {
    return goofy.sendRpcToPlugin(
        'station_setup.station_setup', funcName, ...args);
  }
  async init() {
    const obj = await StationSetup.callRpc('GetProperties');
    for (const [key, description, value] of obj) {
      this.keys.push(key);
      this.keyDesc[key] = description;
      this.properties[key] = value;
    }
  }
  getUpdateFormHtml() {
    let items = [];
    items.push(goog.html.SafeHtml.create('div', {
      'class': 'error-msg',
      'style': goog.html.SafeStyle.create({'color': 'red'})
    }));
    for (const key of this.keys) {
      items.push(goog.html.SafeHtml.create('div', {}, [
        goog.html.SafeHtml.create(
            'div', {}, cros.factory.i18n.i18nLabel(this.keyDesc[key])),
        goog.html.SafeHtml.create('input', {
          'id': 'input-' + key,
          'data-id': key,
          'value': this.properties[key]
        })
      ]));
    }
    return goog.html.SafeHtml.concat(items);
  }
  async updateProperties(element) {
    const inputs = element.getElementsByTagName('input');
    for (const input of inputs) {
      this.properties[input.dataset.id] = input.value;
    }
    return StationSetup.callRpc('UpdateProperties', this.properties);
  }
  static async updateDisplayInfo() {
    const element = $('#station-info')[0];
    const obj = await StationSetup.callRpc('GetProperties');
    let status = [];
    for (const [unused_key, unused_description, value] of obj) {
      status.push(value);
    }
    goog.dom.setTextContent(element, status.join(' / '));
  }
  static async run() {
    const stationSetup = new StationSetup();
    await stationSetup.init();

    const html = stationSetup.getUpdateFormHtml();
    const update = async (element) => {
      for (const input of element.getElementsByTagName('input')) {
        input.disabled = true;
      }
      const ret = await stationSetup.updateProperties(element);
      for (const input of element.getElementsByTagName('input')) {
        input.disabled = false;
      }
      if (ret.success) {
        await StationSetup.updateDisplayInfo();
      } else {
        goog.dom.safe.setInnerHtml(
            element.getElementsByClassName('error-msg')[0],
            cros.factory.i18n.i18nLabel(ret.error_msg));
      }
      return ret;
    };

    return {html, update};
  }
  static async needUpdate() {
    return StationSetup.callRpc('NeedUpdate');
  }
}

/*
 * TODO(pihsun): Have some better way of making things usable from menu item,
 *               instead of polluting goofy object.
 */
goofy.StationSetup = StationSetup;

/**
 * Show the popup for updating station properties.
 */
goofy.showStationSetupDialog = async () => {
  const dialog = new goog.ui.Dialog();
  goofy.registerDialog(dialog);

  cros.factory.Goofy.setDialogTitle(
      dialog, cros.factory.i18n.i18nLabel('Update Station Properties'));
  dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOkCancel());

  const {html, update} = await StationSetup.run();
  dialog.setSafeHtmlContent(html);

  dialog.setVisible(true);

  dialog.listen(goog.ui.Dialog.EventType.SELECT, (event) => {
    if (event.key !== goog.ui.Dialog.ButtonSet.DefaultButtons.OK.key) {
      return;
    }
    dialog.getButtonSet().setAllButtonsEnabled(false);
    event.preventDefault();

    update(dialog.getElement()).then((ret) => {
      if (ret.success) {
        dialog.dispose();
      } else {
        dialog.getButtonSet().setAllButtonsEnabled(true);
      }
    });
  });
};

StationSetup.updateDisplayInfo();
