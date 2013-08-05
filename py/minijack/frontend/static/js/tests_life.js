// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  var oTable = $('#test_table').dataTable({
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

  /* Hack to get column width of tests correct in Chrome */
  setTimeout(function() {
    oTable.fnAdjustColumnSizing(1, true);
  }, 100);

  $('#test_table tbody').on('click', 'tr td img', function() {
    var nTr = $(this).parents('tr')[0];
    if (oTable.fnIsOpen(nTr)) {
      this.src = '/static/images/details_open.png';
      oTable.fnClose(nTr);
    } else {
      this.src = '/static/images/details_close.png';
      oTable.fnOpen(nTr, fnFormatDetails(oTable.fnGetData(nTr)), 'cell');
    }
  });

  $('#buttons_div button').button();
  $('#buttons_div button').on('click', function() {
    var params = aParams;
    params['order'] = $(this).val();
    window.location.href = '?' + $.param(params);
  });

  /*
   * Columns:
   *    0 - detail_icon
   *    1 - name
   *    2 - latest_test_time
   *    3 - num_tested
   *    4 - pass_rate
   *    5 - fail_rate
   *    6 - duration_average
   *    7 - duration_min
   *    8 - duration_max
   *    9 - duration_median
   *   10 - duration_stddev
   *   11 - try_average
   *   12 - try_min
   *   13 - try_max
   *   14 - try_median
   *   15 - try_stddev
   */
  aHiddenColumns = [7, 8, 12, 13];
  for (var i = 0; i < aHiddenColumns.length; i++) {
      oTable.fnSetColumnVis(aHiddenColumns[i], false);
  }
});


function fnFormatDetails(aData) {
  var sOut = '';
  var sPath = $(aData[1]).text().trim();
  var aDeviceList = aaFailedDevices[sPath];

  sOut += '<b>Devices (total: ' + aDeviceList.length.toString() + ')</b>';
  sOut += ' which ran this test (<b>' + sPath + '</b>) but never passed:';
  sOut += '<a href="devices?device_id__in=' + aDeviceList.join(',') + '"';
  sOut += 'class="detail_button">Show DEVICES</a>';

  sOut += '<table class="detail">';
  sOut += '<tr><td>device_id</td>';
  sOut += '<td>serial</td><td>mlb_serial</td><td>last_test_time</td></tr>';
  for (var i = 0; i < aDeviceList.length; i++) {
    var sId = aDeviceList[i];
    sOut += '<tr><td><a href="device/' + sId + '">';
    sOut += sId + '</a>';
    sOut += '</td><td>' + aaDeviceInfo[sId][0];
    sOut += '</td><td>' + aaDeviceInfo[sId][1];
    sOut += '</td><td>' + aaDeviceInfo[sId][2];
    sOut += '</td></tr>';
  }
  sOut += '</table>';

  return sOut;
}

