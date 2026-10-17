function leftText(t) {
  var ms = t * 1000 - Date.now();
  if (ms <= 0) return "Expired";
  var m = Math.floor(ms / 60000), d = Math.floor(m / 1440), h = Math.floor(m % 1440 / 60);
  if (d >= 1) return d + "d " + h + "h remaining";
  if (h >= 1) return h + "h " + (m % 60) + "m remaining";
  return m + "m " + Math.floor(ms / 1000 % 60) + "s remaining";
}
setInterval(function () {
  document.querySelectorAll("[data-exp]").forEach(function (e) { e.textContent = leftText(+e.dataset.exp); });
}, 1000);

var inrFmt = new Intl.NumberFormat("en-IN", {style: "currency", currency: "INR", maximumFractionDigits: 2});
var af = document.getElementById("addform");
if (af) {
  var calcBox = document.getElementById("calc"), priceBox = document.getElementById("f_price");
  var timer = null, rec = null;
  function val(n) { return af.elements[n] ? af.elements[n].value : ""; }
  function refresh() {
    var exp = new Date(val("exp")).getTime() / 1000;
    af.elements["exp_ts"].value = isNaN(exp) ? "" : exp;
    clearTimeout(timer);
    timer = setTimeout(function () {
      fetch("/calc", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({cat: val("cat"), orig: val("orig"), cost: val("cost"), qty: val("qty"),
                              minp: val("minp"), exp: exp, strat: val("strat")})})
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.error) { calcBox.textContent = d.error; rec = null; return; }
          rec = d;
          calcBox.innerHTML = "<table>" +
            "<tr><td>Original price</td><td>" + inrFmt.format(val("orig")) + "</td></tr>" +
            "<tr><td>Recommended discount</td><td>" + d.pct + "%" + (d.floored ? " (held at your minimum price)" : "") + "</td></tr>" +
            "<tr><td>Discount amount</td><td>" + inrFmt.format(d.disc) + " per unit</td></tr>" +
            "<tr><td><b>Recommended price</b></td><td><b>" + inrFmt.format(d.price) + "</b></td></tr>" +
            "<tr><td>Your purchase cost</td><td>" + inrFmt.format(val("cost") || 0) + "</td></tr>" +
            "<tr><td>Potential proceeds (if all sell)</td><td>" + inrFmt.format(d.proceeds) + "</td></tr>" +
            "<tr><td>Potential " + (d.profit < 0 ? "loss" : "profit") + " (not realised)</td><td>" + inrFmt.format(d.profit) + "</td></tr>" +
            "<tr><td>Quantity</td><td>" + val("qty") + "</td></tr>" +
            "<tr><td>Time remaining</td><td>" + leftText(exp) + "</td></tr></table>" +
            (d.critical ? "<div class='warn'>Critical: act now, but only list if the product is still safe and eligible.</div>" : "") +
            "<p class='sub'>Rule-based estimate. It does not guarantee a sale.</p>";
        })
        .catch(function () { calcBox.textContent = "Could not reach the server."; });
    }, 250);
  }
  af.addEventListener("input", refresh);
  af.addEventListener("change", refresh);
  var useBtn = document.getElementById("userec");
  if (useBtn) useBtn.addEventListener("click", function () { if (rec) priceBox.value = rec.price; });
  var file = document.getElementById("scanfile");
  if (file) file.addEventListener("change", function () {
    var f = file.files[0];
    if (!f) return;
    document.getElementById("pv").innerHTML = "<img src='" + URL.createObjectURL(f) +
      "' style='max-width:100%;max-height:200px;margin-top:8px;border-radius:8px'>" +
      "<div class='sub'>Preview only. No fields were extracted.</div>";
  });
}
