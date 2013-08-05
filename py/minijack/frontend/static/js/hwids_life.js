// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  /* Save original headers for later use. */
  var headers = $('thead th');

  var oTable = $('#hwid_table').dataTable({
    'aLengthMenu': [[10, 20, 40, 60, 80, 100, 200, -1],
                    [10, 20, 40, 60, 80, 100, 200, 'All']],
    'aaSorting': [[1, 'asc']],
    'aoColumnDefs': [
      {'bSortable': false, 'aTargets': [0]}
    ],
    'bJQueryUI': true,
    'bScrollCollapse': true,
    'iDisplayLength': 100,
    'oColVis': {
      'aiExclude': [0],
      'sAlign': 'right',
      'sSize': 'css'
    },
    'sDom': '<lCfr><ip>t<ip>',
    'sPaginationType': 'full_numbers',
    'sScrollX': '100%'
  });

  var aDifferenceColumns = [];

  /* Add a select menu for each TH element in the table header */
  headers.each(function(i) {
    if (i >= 2) {
      var data = oTable.fnGetColumnData(i);
      if (fnCheckAllEqual(data)) {
        return;
      }
      aDifferenceColumns.push(i);
      this.innerHTML += fnCreateSelect(data);

      $('select', this).change(function() {
        oTable.fnFilter($(this).val().replace(/ \(.*\)$/, ''), i);
      });
    }
  });

  $('#suite_radio').buttonset().change(function(e) {
    if (e.target.value == 0) {
      /* Show All */
      headers.each(function(i) {
        oTable.fnSetColumnVis(i, true);
      });
    } else {
      /* Show Differences */
      headers.each(function(i) {
        if (i <= 1 || $.inArray(i, aDifferenceColumns) !== -1)
          oTable.fnSetColumnVis(i, true);
        else
          oTable.fnSetColumnVis(i, false);
      });
    }
  });

  /* Hack to get column width of hwid correct in Chrome */
  setTimeout(function() {
    oTable.fnAdjustColumnSizing(1, true);
  }, 100);

  $('#hwid_table tbody').on('click', 'tr td img', function() {
    var nTr = $(this).parents('tr')[0];
    if (oTable.fnIsOpen(nTr)) {
      this.src = '/static/images/details_open.png';
      oTable.fnClose(nTr);
    } else {
      this.src = '/static/images/details_close.png';
      oTable.fnOpen(nTr, fnFormatDetails(oTable.fnGetData(nTr)), 'cell');
    }
  });
});


function fnFormatDetails(aData) {
  var sOut = '';
  var sHwid = aData[1];
  var aDeviceList = aaDevices[sHwid];

  var aDeviceId = $.map(aDeviceList, function(val) {
    return val[0];
  });
  sOut += '<b>Devices (total: ' + aDeviceList.length.toString() + ')</b>';
  sOut += ' have the HWID (<b>' + sHwid + '</b>): ';
  sOut += '<a href="devices?device_id__in=' + aDeviceId.join(',') + '"';
  sOut += 'class="detail_button">Show DEVICES</a>';

  sOut += '<table class="detail">';
  sOut += '<tr><td>device_id</td>';
  sOut += '<td>serial</td><td>mlb_serial</td><td>last_test_time</td></tr>';
  for (var i = 0; i < aDeviceList.length; i++) {
    sOut += '<tr><td><a href="device/' + aDeviceList[i][0] + '">';
    sOut += aDeviceList[i][0] + '</a>';
    sOut += '</td><td>' + aDeviceList[i][1];
    sOut += '</td><td>' + aDeviceList[i][2];
    sOut += '</td><td>' + aDeviceList[i][3];
    sOut += '</td></tr>';
  }
  sOut += '</table>';

  return sOut;
}

function fnCheckAllEqual(data) {
  if (data.length == 0) {
    return true;
  }
  for (i = 1; i < data.length; i++) {
    if (data[i] != data[0]) {
      return false;
    }
  }
  return true;
}
