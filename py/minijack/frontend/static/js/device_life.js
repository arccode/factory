// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  var oTable = $("#test_table").dataTable({
    "aLengthMenu": [[20, 40, 60, 80, 100, 200, -1],
                    [20, 40, 60, 80, 100, 200, "All"]],
    "aaSorting": [[7, "desc"]],
    "aoColumnDefs": [
      {"bSortable": false, "aTargets": [0]},
    ],
    "bJQueryUI": true,
    "bScrollCollapse": true,
    "iDisplayLength": -1,
    "oColVis": {
      "aiExclude": [0],
      "sAlign": "right",
      "sSize": "css",
    },
    "sDom": "<lCfr><ip>t<ip>",
    "sPaginationType": "full_numbers",
    "sScrollX": "100%",
  });

  var aDateColumns = [7, 8];
  var aSelectableColumns = [4, 5, 6, 7, 8, 10, 11];
  var aHiddenColumns = [2, 3, 6, 12];

  /* Add a select menu for each TH element in the table header */
  $("thead th").each(function(i) {
    if ($.inArray(i, aSelectableColumns) != -1) {
      if ($.inArray(i, aDateColumns) !== -1)
        this.innerHTML += fnCreateSelect(oTable.fnGetColumnData(i, fnCutDate));
      else
        this.innerHTML += fnCreateSelect(oTable.fnGetColumnData(i));

      $("select", this).change(function() {
        oTable.fnFilter($(this).val().replace(/ (.*)$/, ""), i);
      });
    }
  });

  $.each(aHiddenColumns, function(index, value) {
    oTable.fnSetColumnVis(value, false);
  });

  $("#test_table tbody tr td img").live("click", function() {
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
  var sInvocation = aData[3];
  if (sInvocation in aaEvents) {
    var aaTestEvents = aaEvents[sInvocation];
    for (var i = 0; i < aaTestEvents.length; i++) {
      sOut += '<tr>';
      sOut += '<td>EVENT: <a href="../event/' + aaTestEvents[i][0] + '">';
      sOut += aaTestEvents[i][1] + '</a></td>';
      sOut += '</tr>';
    }
  }
  sOut += '</table>';

  return sOut;
}
