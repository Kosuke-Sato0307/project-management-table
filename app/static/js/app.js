// 案件管理システム クライアントJS（同梱・外部CDN不使用）
(function () {
  "use strict";

  // 金額欄（data-comma 属性つき）に3桁カンマを自動挿入する。
  // 送信値はカンマ入りだが、サーバ側でカンマを除去して数値化する。
  function formatWithComma(value) {
    // 数字以外を除去
    var digits = (value || "").replace(/[^0-9]/g, "");
    if (digits === "") return "";
    // 先頭の余分なゼロを削る（0のみは0）
    digits = digits.replace(/^0+(?=\d)/, "");
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function attach(el) {
    // 初期表示を整形
    el.value = formatWithComma(el.value);
    el.addEventListener("input", function () {
      var start = el.selectionStart;
      var before = el.value;
      el.value = formatWithComma(el.value);
      // カーソル位置をおおまかに維持
      var diff = el.value.length - before.length;
      try { el.setSelectionRange(start + diff, start + diff); } catch (e) {}
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var inputs = document.querySelectorAll("input[data-comma]");
    for (var i = 0; i < inputs.length; i++) attach(inputs[i]);
  });
})();
