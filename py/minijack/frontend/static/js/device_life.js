// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  var oTable = $('#test_table').dataTable({
    "aLengthMenu": [[20, 40, 60, 80, 100, 200, -1],
                    [20, 40, 60, 80, 100, 200, "All"]],
    "aaSorting": [[6, "desc"]],
    "bJQueryUI": true,
    "bScrollCollapse": true,
    "iDisplayLength": -1,
    "oColVis": {
      "sSize": "css",
      "sAlign": "right",
    },
    "sDom": '<lCfr><ip>t<ip>',
    "sPaginationType": "full_numbers",
    "sScrollX": "100%",
  });

  var aDateColumns = [6, 7];
  var aSelectableColumns = [3, 4, 5, 6, 7, 9, 10];
  var aHiddenColumns = [1, 2, 5];

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

  $.each(aHiddenColumns, function(index, value) {
    oTable.fnSetColumnVis(value, false);
  });

});
