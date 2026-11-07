/* Display-level de-identification: the demo runs on one university's public notices, but shows them as a generic
 * campus (Campus A / Campus B, "the university", "the logistics department"). Only what is displayed changes; the
 * system itself reads and answers the original notices (the back end maps "A校区"/"B校区" typed by a visitor back).
 * Loaded by index.html and cseg.html; the screenshot scripts of the paper inject the same file. */
(function () {
  var MAP = [
    ["CondQA-RUC", "CondQA-Campus"],
    ["中国人民大学", "某高校"], ["人民大学", "某高校"], ["温馨人大", "学校公众号"], ["RUC", ""], ["人大", "本校"],
    ["综合服务保障体系", "高校后勤"], ["综合保障部", "后勤部门"], ["综保部", "后勤部门"], ["综合服务门户", "服务门户"],
    ["中关村校区", "A校区"], ["通州校区", "B校区"], ["中关村", "A校区"], ["潞城站", "B校区附近地铁站"],
    ["潞城", "B校区"], ["通州", "B校区"],
    ["Renmin University of China", "the university"], ["Renmin University", "the university"],
    ["General Services Department", "logistics department"], ["Wenxin Renda", "the university's WeChat account"],
    ["Comprehensive Services Portal", "service portal"],
    ["Zhongguancun campus", "Campus A"], ["Zhongguancun Campus", "Campus A"], ["Tongzhou campus", "Campus B"],
    ["Tongzhou Campus", "Campus B"], ["Zhongguancun", "Campus A"], ["Tongzhou", "Campus B"], ["Lucheng", "Campus B"]
  ];
  function deid(s) {
    if (!s) return s;
    for (var i = 0; i < MAP.length; i++) if (s.indexOf(MAP[i][0]) >= 0) s = s.split(MAP[i][0]).join(MAP[i][1]);
    return s;
  }
  window.deid = deid;
  var ATTRS = ["title", "placeholder", "aria-label", "alt"];
  function fixText(n) {
    var v = n.nodeValue, w = deid(v);
    if (w !== v) n.nodeValue = w;
  }
  function fixEl(el) {
    for (var i = 0; i < ATTRS.length; i++) {
      var v = el.getAttribute && el.getAttribute(ATTRS[i]);
      if (v) { var w = deid(v); if (w !== v) el.setAttribute(ATTRS[i], w); }
    }
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { fixText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) {
      var tag = root.tagName;
      if (tag === "SCRIPT" || tag === "STYLE" || tag === "TEXTAREA" || tag === "INPUT") return;
      fixEl(root);
    }
    var tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
      acceptNode: function (n) {
        if (n.nodeType === 1 && (n.tagName === "SCRIPT" || n.tagName === "STYLE" || n.tagName === "TEXTAREA"))
          return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var n;
    while ((n = tw.nextNode())) { if (n.nodeType === 3) fixText(n); else fixEl(n); }
  }
  function start() {
    walk(document.body);
    document.title = deid(document.title);
    new MutationObserver(function (ms) {
      for (var i = 0; i < ms.length; i++) {
        var m = ms[i];
        if (m.type === "characterData") fixText(m.target);
        else if (m.type === "attributes") fixEl(m.target);
        else for (var j = 0; j < m.addedNodes.length; j++) walk(m.addedNodes[j]);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true,
      attributeFilter: ATTRS });
  }
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
})();
