/* Minimal runtime for RAGcat prototype pages.
   Template syntax used in the page:
     {{path}}                       text or attribute hole (path = a.b.c from renderVals())
     <template data-if="{{x}}">     rendered when x is truthy
     <template data-for="{{list}}" data-as="item">  repeated for each item
     onClick="{{fn}}" / onChange="{{fn}}"           event handlers from renderVals()
   Component: class Component extends DCLogic { state = {...}; renderVals() { return {...} } }
   Props come from data-props defaults and can be overridden with ?prop=value in the URL. */
class DCLogic {
  constructor(props) { this.props = props || {}; this.state = {}; }
  setState(p) {
    const patch = typeof p === "function" ? p(this.state, this.props) : p;
    this.state = Object.assign({}, this.state, patch);
    DC.render();
  }
}

const DC = {
  get(expr, scopes) {
    const path = expr.trim();
    if (path === "true") return true;
    if (path === "false") return false;
    if (path === "null") return null;
    if (/^-?\d+(\.\d+)?$/.test(path)) return Number(path);
    if (/^(["']).*\1$/.test(path)) return path.slice(1, -1);
    const parts = path.split(".");
    let v;
    let found = false;
    for (const s of scopes) {
      if (s && typeof s === "object" && parts[0] in s) { v = s[parts[0]]; found = true; break; }
    }
    if (!found) return undefined;
    for (let i = 1; i < parts.length; i++) {
      if (v == null) return undefined;
      v = v[parts[i]];
    }
    return v;
  },
  interp(str, scopes) {
    const single = str.match(/^\s*\{\{([^}]*)\}\}\s*$/);
    if (single) return DC.get(single[1], scopes);
    return str.replace(/\{\{([^}]*)\}\}/g, (_, e) => {
      const v = DC.get(e, scopes);
      return v == null || v === false ? "" : String(v);
    });
  },
  truthy(v) { return !!v && v !== "false"; },
  BOOL: new Set(["disabled", "checked", "selected", "hidden", "readonly", "required", "open"]),
  build(src, out, scopes) {
    for (const n of src.childNodes) {
      if (n.nodeType === 3) {
        let t = n.data;
        if (t.includes("{{")) {
          const v = DC.interp(t, scopes);
          t = v == null || v === false ? "" : String(v);
        }
        out.appendChild(document.createTextNode(t));
        continue;
      }
      if (n.nodeType !== 1) continue;
      if (n.tagName === "TEMPLATE" && n.hasAttribute("data-if")) {
        if (DC.truthy(DC.interp(n.getAttribute("data-if"), scopes))) DC.build(n.content, out, scopes);
        continue;
      }
      if (n.tagName === "TEMPLATE" && n.hasAttribute("data-for")) {
        const list = DC.interp(n.getAttribute("data-for"), scopes) || [];
        const as = n.getAttribute("data-as") || "item";
        list.forEach((item, i) => DC.build(n.content, out, [{ [as]: item, $index: i }].concat(scopes)));
        continue;
      }
      const el = n.cloneNode(false);
      for (const a of Array.from(n.attributes)) {
        if (!a.value.includes("{{")) continue;
        const name = a.name;
        const v = DC.interp(a.value, scopes);
        if (name.startsWith("on")) {
          el.removeAttribute(name);
          if (typeof v === "function") el.addEventListener(name.slice(2), v);
          continue;
        }
        if (DC.BOOL.has(name)) {
          if (DC.truthy(v)) el.setAttribute(name, ""); else el.removeAttribute(name);
          if (name === "checked") el.checked = DC.truthy(v);
          continue;
        }
        if (v == null || (v === false && !name.startsWith("aria-"))) { el.removeAttribute(name); continue; }
        el.setAttribute(name, String(v));
      }
      DC.build(n, el, scopes);
      out.appendChild(el);
    }
  },
  render() {
    const vals = DC.inst.renderVals ? DC.inst.renderVals() : {};
    const frag = document.createDocumentFragment();
    DC.build(DC.tpl.content, frag, [vals]);
    const active = document.activeElement && document.activeElement.id;
    DC.root.replaceChildren(frag);
    if (active) { const f = document.getElementById(active); if (f) f.focus(); }
  },
  mount(Component, propSpec) {
    const props = {};
    for (const [k, spec] of Object.entries(propSpec || {})) {
      if (!k.startsWith("$") && spec && "default" in spec) props[k] = spec.default;
    }
    for (const [k, raw] of new URLSearchParams(location.search)) {
      props[k] = raw === "true" ? true : raw === "false" ? false : raw;
    }
    DC.tpl = document.getElementById("dc-template");
    DC.root = document.getElementById("dc-root");
    DC.inst = new Component(props);
    DC.render();
  }
};
