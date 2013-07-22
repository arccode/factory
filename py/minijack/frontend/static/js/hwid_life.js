// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  var oTable = $("#hwid_table").dataTable({
    "aLengthMenu": [[20, 40, 60, 80, 100, 200, -1],
                    [20, 40, 60, 80, 100, 200, "All"]],
    "aaSorting": [[1, "asc"]],
    "aoColumnDefs": [
      {"bSortable": false, "aTargets": [0]},
    ],
    "bJQueryUI": true,
    "bScrollCollapse": true,
    "iDisplayLength": 100,
    "oColVis": {
      "aiExclude": [0],
      "sAlign": "right",
      "sSize": "css",
    },
    "sDom": "<lCfr><ip>t<ip>",
    "sPaginationType": "full_numbers",
    "sScrollX": "100%",
  });

  /* Add a select menu for each TH element in the table header */
  $("thead th").each(function(i) {
    if (i >= 2 && i <= 27) {
      this.innerHTML += fnCreateSelect(oTable.fnGetColumnData(i));

      $("select", this).change(function() {
        oTable.fnFilter($(this).val().replace(/ \(.*\)$/, ""), i);
      });
    }
  });

  /* Hack to get column width of hwid correct in Chrome */
  setTimeout(function() {
    oTable.fnAdjustColumnSizing(1, true);
  }, 100);

  $("#hwid_table tbody tr td img").live("click", function() {
    var nTr = $(this).parents("tr")[0];
    if (oTable.fnIsOpen(nTr)) {
      this.src = "/static/images/details_open.png";
      oTable.fnClose(nTr);
    } else {
      this.src = "/static/images/details_close.png";
      oTable.fnOpen(nTr, fnFormatDetails(oTable.fnGetData(nTr)), "cell");
    }
  });
});


function fnFormatDetails(aData) {
  var sOut = '';
  var sHwid = aData[1];
  var aaDeviceList = aaDevices[sHwid];

  sOut += '<table class="detail">';
  sOut += '<tr>';
  sOut += '<td>Total: ' + aaDeviceList.length.toString() + '</td>';
  sOut += '<td>serial</td><td>mlb_serial</td><td>last_test_time</td></tr>';
  for (var i = 0; i < aaDeviceList.length; i++) {
    sOut += '<tr><td>DEVICE: <a href="../device/' + aaDeviceList[i][0] + '">';
    sOut += aaDeviceList[i][0] + '</a>';
    sOut += '</td><td>' + aaDeviceList[i][1];
    sOut += '</td><td>' + aaDeviceList[i][2];
    sOut += '</td><td>' + aaDeviceList[i][3];
    sOut += '</td></tr>';
  }
  sOut += '</ul>';

  return sOut;
}

