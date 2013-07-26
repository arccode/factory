// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

$(document).ready(function() {
  $('#add_button').button({
    icons: {primary: 'ui-icon-plus'},
    text: false
  });

  $('.remove_button').button({
    icons: {primary: 'ui-icon-minus'},
    text: false
  });

  $('#help_button').button({
    icons: {primary: 'ui-icon-help'},
    text: false
  });

  $('#filter_submit').button();

  $('#filter_title').on('click', function() {
    $('#filter_form').toggleClass('hidden');
  });

  $('#help_button').on('click', function() {
    $('#help_div').toggleClass('hidden');
  });

  $('#filter_list').on('click', '.remove_button', function() {
    $(this).parent().remove();
  });
  $('#filter_list').on('click', '#add_button', fnAddFilterRow);
  $('#filter_submit').on('click', function() {
    var oQuery = fnBuildFilterQuery();
    if (oQuery == null) {
      return;
    }
    for (var k in aParams) {
      if (k.indexOf('__') == -1) {
        oQuery[k] = aParams[k];
      }
    }
    window.location.href = '?' + $.param(oQuery);
  });

  $.datepicker.setDefaults({dateFormat: 'yy-mm-dd'});

  $('#filter_list').on('focus', 'input[type=text]', function() {
    var oInput = $(this);
    var sTarget = oInput.parent().find('select[name=target]').val();
    if (sTarget in aEnumerateKeys) {
      oInput.autocomplete({
        minLength: 0,
        source: aEnumerateKeys[sTarget],
        position: {
          my: 'right top',
          at: 'right bottom',
          collision: 'none'
        },
        select: function(e, ui) {
          oInput.blur();
        }
      });
      oInput.autocomplete('search', '');
      oInput.data('has_enumerate', true);
    } else {
      if (oInput.data('has_enumerate')) {
        oInput.autocomplete('destroy');
        oInput.data('has_enumerate', false);
      }
    }

    if (fnEndsWith(sTarget, '_time')) {
      oInput.datepicker();
      oInput.data('has_datepicker', true);
    } else {
      if (oInput.data('has_datepicker')) {
        oInput.data('has_datepicker', false);
        oInput.datepicker('destroy');
      }
    }
  });

});


function fnEndsWith(str, suffix) {
  return str.indexOf(suffix, str.length - suffix.length) !== -1;
}


function fnAddFilterRow() {
  var oRow = $(fnBuildFilterRow());
  oRow.find('.remove_button').button({
    icons: {primary: 'ui-icon-minus'},
      text: false
  });
  $('#filter_list').append(oRow);
}


function fnBuildFilterRow() {
  var sOut = '<li class="filter_rule">';
  sOut += '<button class="remove_button" type="button">Remove</button>';
  sOut += ' <input name="inverse" type="checkbox"/>not';

  sOut += ' <select name="target">';
  for (var i = 0; i < aaFilterKeys.length; i++) {
    sOut += '<option value="' + aaFilterKeys[i] + '">' +
        aaFilterKeys[i] + '</option>';
  }
  sOut += '</select>';

  aOp = ['exact', 'in', 'gt', 'gte', 'lt', 'lte', 'contains', 'regex'];
  aOpName = ['=', 'in', '&gt;', '&gt;=', '&lt;', '&lt;=', 'contains', 'regex'];

  sOut += ' <select name="op">';
  for (var i = 0; i < aOp.length; i++) {
    sOut += '<option value="' + aOp[i] + '">' + aOpName[i] + '</option>';
  }
  sOut += '</select>';

  sOut += ' <input type="text" value=""></input>';
  sOut += '</li>';
  return sOut;
}


function fnBuildFilterQuery() {
  var oOut = {};
  var bError = false;
  $('li.filter_rule').each(function(i) {
    var oRow = $(this);
    var sKey = oRow.find('select[name=target]').val();
    var sOp = oRow.find('select[name=op]').val();
    if (fnEndsWith(sKey, '_time') && (sOp == 'exact' || sOp == 'in')) {
      // Should not use = or in on time field
      alert('Error in rule #' + (i + 1).toString() +
        ': Should not use "=" or "in" on time field, use "contains" instead.');
      bError = true;
      return;
    }
    sKey += '__' + sOp;
    if (oRow.find('input[name=inverse]').prop('checked')) {
      sKey += '__not';
    }
    var sValue = oRow.find('input[type=text]').val();
    // Default row have value == '', ignore them.
    if (sValue != '') {
      oOut[sKey] = sValue;
    }
  });
  if (bError) {
    return null;
  }
  return oOut;
}
