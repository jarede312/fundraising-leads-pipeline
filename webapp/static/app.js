(function () {
  "use strict";

  function isTypingTarget(el) {
    return el && (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA");
  }

  // ---- All Schools: j/k row selection, Enter to open, click to open ----
  //
  // Delegated on #results rather than bound to #school-table directly: htmx replaces
  // the table's innerHTML on every filter/sort/page change, which detaches any
  // listener bound to the old <table> element. #results itself is the swap target
  // and is never replaced, so binding there survives every swap - the previous
  // version re-queried the table once at load and went silently dead after the
  // first filter change.
  var results = document.getElementById("results");
  if (results) {
    var selected = -1;

    function rows() {
      return results.querySelectorAll("tbody tr.school-row");
    }

    function select(i) {
      var r = rows();
      if (!r.length) return;
      if (selected >= 0 && r[selected]) r[selected].classList.remove("selected");
      selected = Math.max(0, Math.min(i, r.length - 1));
      r[selected].classList.add("selected");
      r[selected].scrollIntoView({ block: "nearest" });
    }

    document.addEventListener("keydown", function (e) {
      if (isTypingTarget(e.target)) return;
      if (!document.getElementById("school-table")) return;
      if (e.key === "j") { e.preventDefault(); select(selected + 1); }
      else if (e.key === "k") { e.preventDefault(); select(selected < 0 ? 0 : selected - 1); }
      else if (e.key === "Enter") {
        if (selected >= 0) {
          var r = rows()[selected];
          if (r) window.location.href = r.dataset.href;
        }
      }
    });

    results.addEventListener("click", function (e) {
      var r = e.target.closest("tr.school-row");
      if (r) window.location.href = r.dataset.href;
    });

    // A fresh table (new rows, or the same rows re-rendered) has no meaningful
    // prior selection - reset rather than pointing at a row index that may now
    // hold a different school.
    document.body.addEventListener("htmx:afterSwap", function (e) {
      if (e.detail.target === results) selected = -1;
    });
  }

  document.body.addEventListener("htmx:afterRequest", function (e) {
    var path = e.detail.pathInfo && e.detail.pathInfo.requestPath;
    if (!(e.detail.successful && path && /\/actions$/.test(path))) return;

    document.querySelectorAll(".notes-input").forEach(function (i) { i.value = ""; });

    // the click that fired this request gets a visible "logged" state - otherwise
    // the only feedback is the timeline changing somewhere else on the page, which
    // reads as the button having done nothing.
    var btn = e.detail.elt;
    if (btn && btn.classList && btn.classList.contains("log-btn")) {
      btn.classList.add("just-logged");
      setTimeout(function () { btn.classList.remove("just-logged"); }, 1400);
    }
  });

  // ---- Failed writes: htmx never swaps a non-2xx response into its hx-target, so
  // without this a rejected save (a bad date, a stale id) produced no visible change
  // at all - the rep would click Save again, or just assume it worked. The server
  // sends back a small "_error_banner.html" fragment on failure; float it in a fixed
  // banner regardless of what the request's own hx-target was. ----
  var errorBannerHost = document.getElementById("error-banner-host");
  document.body.addEventListener("htmx:responseError", function (e) {
    if (errorBannerHost && e.detail.xhr) {
      errorBannerHost.innerHTML = e.detail.xhr.responseText;
    }
  });
  document.body.addEventListener("htmx:sendError", function () {
    if (errorBannerHost) {
      errorBannerHost.innerHTML =
        '<div class="error-banner" role="alert"><span class="error-banner-icon">&#9888;</span>' +
        "<span>Couldn't reach the server - check your connection and try again.</span>" +
        '<button type="button" class="error-banner-dismiss" aria-label="Dismiss">&times;</button></div>';
    }
  });
  document.body.addEventListener("click", function (e) {
    if (e.target.classList && e.target.classList.contains("error-banner-dismiss")) {
      var banner = e.target.closest(".error-banner");
      if (banner) banner.remove();
    }
  });

  if (document.querySelector(".detail-page")) {
    document.addEventListener("keydown", function (e) {
      if (isTypingTarget(e.target)) return;
      if (e.key === "Escape") {
        var back = document.querySelector(".back-link");
        if (back) window.location.href = back.getAttribute("href");
        return;
      }
      if (e.key === "n") {
        // The General/Front Office card is the one standing, always-present entry
        // point on the page - see _contacts_section.html - so it's the target for
        // both the notes shortcut and the c/l/e/v/m log shortcuts below. Earlier
        // versions of this file looked for a "#notes-default" / ".primary-log" that
        // no template has ever rendered, so neither shortcut ever fired.
        var notes = document.getElementById("notes-office");
        if (notes) { e.preventDefault(); notes.focus(); }
        return;
      }
      var btn = document.querySelector('.log-btn[data-scope="office"][data-shortcut="' + e.key + '"]');
      if (btn) { e.preventDefault(); btn.click(); return; }

      if (document.querySelector(".queue-page")) {
        if (e.key === "Enter") {
          var next = document.getElementById("queue-next");
          if (next) { e.preventDefault(); window.location.href = next.getAttribute("href"); }
        } else if (e.key === "p" || e.key === "ArrowLeft") {
          var prev = document.querySelector(".queue-nav-btn:not(.disabled)");
          if (prev && prev.textContent.indexOf("Previous") >= 0) {
            e.preventDefault(); window.location.href = prev.getAttribute("href");
          }
        }
      }
    });
  }
})();
