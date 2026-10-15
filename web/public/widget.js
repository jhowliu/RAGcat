/* RAGcat Website widget loader (docs/api-design.md §7). An owner pastes one line before </body>:
     <script src="https://<RAGcat>/widget.js" data-assistant="ast_…" async></script>
   Optional: data-lang="zh" or "en" (otherwise the host page's lang, then the browser's).
   It draws a launcher inside a shadow root, so the host page's CSS can't reach it, and on first
   open an iframe of RAGcat's own frame page. Nothing else runs on the host page, and nothing from
   the conversation is shared with it: the frame only ever posts "close". */
(function () {
  'use strict'
  var script = document.currentScript
  if (!script || window.__ragcatWidget) return
  var aid = script.getAttribute('data-assistant')
  if (!aid) return
  window.__ragcatWidget = true

  var origin = new URL(script.src, location.href).origin
  var lang = /^zh/i.test(script.getAttribute('data-lang') || document.documentElement.lang || navigator.language || '') ? 'zh' : 'en'
  var text = lang === 'zh' ? { open: '提問', close: '關閉提問視窗', frame: '提問' } : { open: 'Ask a question', close: 'Close questions', frame: 'Questions' }
  // The api serves the frame page; its frame-ancestors header lists the owner's sites. The dev demo
  // Assistants ("demo…", web/widget-demo.html) answer from a script in the static page instead.
  var frame = /^demo(-|$)/.test(aid) ? '/widget.html?aid=' + encodeURIComponent(aid) + '&' : '/v1/widget/' + encodeURIComponent(aid) + '/frame?'
  var src = origin + frame + 'lang=' + lang

  // Values mirror web/src/theme/tokens.css; the host page has no access to RAGcat's stylesheet.
  var CSS =
    ':host{all:initial;--ink:#1B1A19;--ink-hover:#34322F;--surface:#FFFFFF;--canvas:#F7F7F5;--border:#E7E5E1;' +
    '--overlay:0 4px 10px rgba(27,26,25,.06),0 18px 44px rgba(27,26,25,.14);--ease:cubic-bezier(.16,1,.3,1)}' +
    '.launcher{position:fixed;right:20px;bottom:20px;z-index:2147483000;width:56px;height:56px;display:grid;place-items:center;' +
    'padding:0;border:0;border-radius:16px;background:var(--ink);color:var(--surface);box-shadow:var(--overlay);cursor:pointer;' +
    'transition:background-color 160ms var(--ease),transform 160ms var(--ease)}' +
    '.launcher:hover{background:var(--ink-hover)}' +
    '.launcher:active{transform:translateY(1px)}' +
    '.launcher:focus-visible{outline:2px solid var(--ink);outline-offset:3px}' +
    '.launcher svg{display:block}' +
    '.panel{position:fixed;right:20px;bottom:88px;z-index:2147483000;width:min(380px,calc(100vw - 40px));' +
    'height:min(640px,calc(100vh - 108px));overflow:hidden;border:1px solid var(--border);border-radius:14px;' +
    'background:var(--canvas);box-shadow:var(--overlay);opacity:0;transform:translateY(8px);transform-origin:100% 100%;' +
    'transition:opacity 160ms var(--ease),transform 160ms var(--ease)}' +
    '.panel.open{opacity:1;transform:none}' +
    '.panel[hidden]{display:none}' +
    // Until the frame has loaded, the panel holds the mark on the canvas instead of a blank sheet.
    '.loading{position:absolute;inset:0;display:grid;place-items:center}' +
    '.loading span{width:48px;height:48px;display:grid;place-items:center;border:1px solid var(--border);border-radius:50%;' +
    'background:var(--surface)}' +
    'iframe{position:relative;display:block;width:100%;height:100%;border:0;color-scheme:light;opacity:0;' +
    'transition:opacity 160ms var(--ease)}' +
    'iframe.ready{opacity:1}' +
    '@media (max-width:480px){.panel{inset:0;width:auto;height:auto;border:0;border-radius:0}' +
    '.launcher[aria-expanded="true"]{display:none}}' +
    '@media (prefers-reduced-motion:reduce){.panel,.launcher,iframe{transition:none}}'

  // The mark: the mascot's head (web/src/components/ui.tsx Mark). Its white face reads on ink.
  var MARK =
    '<svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true"><g fill="none" stroke="#1B1A19" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M5.2 15.5 6.6 2.6l5.8 5.8h7.2l5.8-5.8 1.4 12.9c.2 6-4.4 11.7-10.8 11.7S5 21.5 5.2 15.5Z" fill="#FFFFFF" stroke-width="1.8"/>' +
    '<path d="M7.7 5.6l2.9 3.1-3.4 2.5ZM24.3 5.6l-2.9 3.1 3.4 2.5Z" fill="#FFD43B" stroke="none"/>' +
    '<circle cx="12" cy="16.4" r="3.4" stroke-width="1.3"/><circle cx="20" cy="16.4" r="3.4" stroke-width="1.3"/>' +
    '<path d="M15.4 16.2h1.2M14.3 22.6q.85.9 1.7 0 .85.9 1.7 0" stroke-width="1"/></g>' +
    '<g fill="#1B1A19"><circle cx="12" cy="16.7" r="1"/><circle cx="20" cy="16.7" r="1"/><path d="M15.1 20.5h1.8l-.9 1.1Z"/></g></svg>'
  var DOWN =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>'

  function mount() {
    var host = document.createElement('div')
    host.setAttribute('data-ragcat-widget', '')
    var root = host.attachShadow({ mode: 'open' })
    root.innerHTML =
      '<style>' + CSS + '</style><div class="panel" id="panel" hidden><div class="loading" aria-hidden="true"><span>' + MARK + '</span></div></div>' +
      '<button class="launcher" type="button" aria-controls="panel"></button>'
    var panel = root.querySelector('.panel')
    var button = root.querySelector('.launcher')
    var frame = null
    var isOpen = false

    function render() {
      button.innerHTML = isOpen ? DOWN : MARK
      button.setAttribute('aria-expanded', String(isOpen))
      button.setAttribute('aria-label', isOpen ? text.close : text.open)
      button.title = isOpen ? text.close : text.open
    }
    function focusFrame() {
      if (!frame || !isOpen) return
      frame.focus()
      frame.contentWindow.postMessage({ type: 'ragcat:open' }, origin)
    }
    function open() {
      if (!frame) {
        frame = document.createElement('iframe')
        frame.src = src
        frame.title = text.frame
        frame.addEventListener('load', function () {
          frame.classList.add('ready')
          var loading = panel.querySelector('.loading')
          if (loading) loading.remove()
          focusFrame()
        })
        panel.appendChild(frame)
      }
      isOpen = true
      panel.hidden = false
      void panel.offsetWidth // start the transition from the closed state
      panel.classList.add('open')
      render()
      focusFrame()
    }
    function close() {
      isOpen = false
      panel.classList.remove('open')
      render()
      button.focus()
      setTimeout(function () {
        if (!isOpen) panel.hidden = true
      }, 160)
    }

    button.addEventListener('click', function () {
      if (isOpen) close()
      else open()
    })
    window.addEventListener('message', function (e) {
      if (e.origin === origin && frame && e.source === frame.contentWindow && e.data && e.data.type === 'ragcat:close') close()
    })
    render()
    document.body.appendChild(host)
  }

  if (document.body) mount()
  else document.addEventListener('DOMContentLoaded', mount)
})()
