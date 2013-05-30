// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  var oTable = $('#device_table').dataTable({
    "aLengthMenu": [[20, 40, 60, 80, 100, 200, -1],
                    [20, 40, 60, 80, 100, 200, "All"]],
    "aaSorting": [[3, "desc"]],
    "bJQueryUI": true,
    "bScrollCollapse": true,
    "iDisplayLength": 100,
    "oColVis": {
      "sSize": "css",
      "sAlign": "right",
    },
    "sDom": '<lCfr><ip>t<ip>',
    "sPaginationType": "full_numbers",
    "sScrollX": "100%",
  });

  var aDateColumns = [1, 3, 8, 17];
  var aSelectableColumns = [1, 2, 3, 6, 8, 9, 10, 13, 14, 15, 17];

  /* Add a select menu for each TH element in the table header */
  $("thead th").each(function(i) {
    if ($.inArray(i, aSelectableColumns) != -1) {
      if ($.inArray(i, aDateColumns) !== -1)
        this.innerHTML += fnCreateSelect(oTable.fnGetColumnData(i, fnCutDate));
      else
        this.innerHTML += fnCreateSelect(oTable.fnGetColumnData(i));

      $('select', this).change(function() {
        oTable.fnFilter($(this).val(), i);
      });
    }
  });

  $("#suite_radio").buttonset().change(function(e) {
    fnSelectSuite(e.target.value);
  });

  fnSelectSuite(0);
});


function fnSelectSuite(iSuite) {
  /*
   * Columns:
   *    0 - device_id
   *    1 - goofy_init_time
   *    2 - latest_test
   *    3 - test_time
   *    4 - serial
   *    5 - mlb_serial
   *    6 - hwid
   *    7 - ips
   *    8 - ips_time
   *    9 - latest_ended_test
   *   10 - ended_status
   *   11 - c_passed
   *   12 - c_failed
   *   13 - mj_status
   *   14 - latest_note_lv
   *   15 - note_name
   *   16 - note_text
   *   17 - note_time
   */
  var iTotalColumns = 18
  var aaVisibleColumns = [
    [0, 2, 3, 4, 5, 6, 7, 13],
    [0, 1, 2, 3, 9, 10, 11, 12],
    [0, 2, 3, 14, 15, 16, 17],
  ];
  var oTable = $('#device_table').dataTable();

  for (var i = 0; i < iTotalColumns; i++) {
    if ($.inArray(i, aaVisibleColumns[iSuite]) !== -1)
      oTable.fnSetColumnVis(i, true);
    else
      oTable.fnSetColumnVis(i, false);
  }
}
