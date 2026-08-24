(function () {
  "use strict";

  function isTypingTarget(el) {
    return el && (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA");
  }

  var table = document.getElementById("school-table");
  if (table) {
    var selected = -1;

    function rows() {
      return table.querySelectorAll("tbody tr.school-row");
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
      if (e.key === "j") { e.preventDefault(); select(selected + 1); }
      else if (e.key === "k") { e.preventDefault(); select(selected < 0 ? 0 : selected - 1); }
      else if (e.key === "Enter") {
        if (selected >= 0) {
          var r = rows()[selected];
          if (r) window.location.href = r.dataset.href;
        }
      }
    });

    rows().forEach(function (r) {
      r.addEventListener("click", function () { window.location.href = r.dataset.href; });
    });

    // htmx swaps #results (and this table with it) on filter changes - selection
    // state resets naturally since the old row elements are gone.
    document.body.addEventListener("htmx:afterSwap", function () { selected = -1; });
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

  if (document.querySelector(".detail-page")) {
    document.addEventListener("keydown", function (e) {
      if (isTypingTarget(e.target)) return;
      if (e.key === "Escape") {
        var back = document.querySelector(".back-link");
        if (back) window.location.href = back.getAttribute("href");
        return;
      }
      if (e.key === "n") {
        var notes = document.getElementById("notes-default");
        if (notes) { e.preventDefault(); notes.focus(); }
        return;
      }
      var btn = document.querySelector('.primary-log .log-btn[data-shortcut="' + e.key + '"]');
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
