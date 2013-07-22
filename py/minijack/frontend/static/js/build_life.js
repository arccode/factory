// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  var oTable = $("#device_table").dataTable({
    "aLengthMenu": [[20, 40, 60, 80, 100, 200, -1],
                    [20, 40, 60, 80, 100, 200, "All"]],
    "aaSorting": [[4, "desc"]],
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

  var aDateColumns = [2, 4, 9, 18];
  var aSelectableColumns = [2, 3, 4, 7, 9, 10, 11, 14, 15, 16, 18];

  /* Add a select menu for each TH element in the table header */
  $("thead th").each(function(i) {
    if ($.inArray(i, aSelectableColumns) != -1) {
      if ($.inArray(i, aDateColumns) !== -1)
        this.innerHTML += fnCreateSelect(oTable.fnGetColumnData(i, fnCutDate));
      else
        this.innerHTML += fnCreateSelect(oTable.fnGetColumnData(i));

      $("select", this).change(function() {
        oTable.fnFilter($(this).val().replace(/ \(.*\)$/, ""), i);
      });
    }
  });

  $("#suite_radio").buttonset().change(function(e) {
    fnSelectSuite(e.target.value);
  });

  fnSelectSuite(0);

  $("#device_table tbody tr td img").live("click", function() {
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
  var sOut = '<table class="detail">';
  var aIp = aData[8].split(/, /);
  for (var i = 0; i < aIp.length; i++) {
    if (aIp[i]) {
      var aKeyValue = aIp[i].split('=')
      sOut += '<tr>';
      sOut += '<th>' + aKeyValue[0] + '</th>'
      sOut += '<td>' + aKeyValue[1] + '</td>';
      sOut += '<td>' + aData[9] + '</td>';
      sOut += '<td><button id="ping" disabled>Ping</button>';
      sOut += '<button id="ssh" disabled>SSH</button>';
      sOut += '<button id="screenshot" disabled>Screenshot</button></td>';
      sOut += '</tr>';
    }
  }
  sOut += '<tr><td><button id="add_note" disabled>Add Note</button></td>';
  sOut += '<td colspan="3"></td></tr>';
  if (aData[15]) {
    sOut += '<tr><th>' + aData[15] + '</th>';
    sOut += '<td>' + aData[16] + '</td>';
    sOut += '<td>' + aData[18] + '</td>';
    sOut += '<td>' + aData[17] + '</td></tr>';
  }
  sOut += '</table>';

  return sOut;
}


function fnSelectSuite(iSuite) {
  /*
   * Columns:
   *    0 - detail_icon
   *    1 - device_id
   *    2 - goofy_init_time
   *    3 - latest_test
   *    4 - test_time
   *    5 - serial
   *    6 - mlb_serial
   *    7 - hwid
   *    8 - ips
   *    9 - ips_time
   *   10 - latest_ended_test
   *   11 - ended_status
   *   12 - c_passed
   *   13 - c_failed
   *   14 - mj_status
   *   15 - latest_note_lv
   *   16 - note_name
   *   17 - note_text
   *   18 - note_time
   */
  var iTotalColumns = 19
  var aaVisibleColumns = [
    [0, 1, 3, 4, 5, 6, 7, 14],
    [0, 2, 3, 4, 10, 11, 12, 13],
    [0, 3, 4, 15, 16, 17, 18],
  ];
  var oTable = $("#device_table").dataTable();

  for (var i = 0; i < iTotalColumns; i++) {
    if ($.inArray(i, aaVisibleColumns[iSuite]) !== -1)
      oTable.fnSetColumnVis(i, true);
    else
      oTable.fnSetColumnVis(i, false);
  }
}
