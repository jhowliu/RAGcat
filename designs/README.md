# RAGcat 設計交付包（給 Claude Code）

這個資料夾是 RAGcat 正式版（H3）的設計交付包，給工程師與 Claude Code 使用。

## 怎麼用

1. 把整個 `ragcat-design/` 資料夾放進專案，例如 `design/`。
2. 在專案根目錄的 `CLAUDE.md` 加一行，讓 Claude Code 每次做介面時自動照規範：

   ```
   做任何 UI 前，先讀 design/CLAUDE.md，並遵守其中規則。
   ```

3. 交代工作時指定頁面，例如：

   > 依照 design/DESIGN.md 第 10 節 P05 和 design/prototypes/05-review.html，用 React 實作 Review & test 頁。只能用 design/tokens 的 token。完成後用 Playwright 截 1440 和 390 的圖，跟 design/screens 比對並修正差異。

## 內容

| 路徑 | 用途 |
|---|---|
| `CLAUDE.md` | 給 Claude Code 的規則：閱讀順序、硬性規定、驗收方式 |
| `DESIGN.md` | 完整規格：色彩、字體、間距、每個元件的細節、7 個頁面、文案、無障礙 |
| `tokens/tokens.css` | 所有數值（CSS 變數），是唯一的數值來源 |
| `tokens/tokens.json` | 同上，JSON 格式（給其他工具或 Figma 外掛匯入） |
| `tokens/tailwind.preset.js` | Tailwind 專案用 |
| `styles/app.css`、`styles/landing.css` | 原型實際使用的 CSS，顏色已換成 token |
| `prototypes/*.html` | 7 個可互動頁面，直接用瀏覽器打開 `index.html` |
| `screens/desktop`、`screens/mobile` | 1440 與 390 的截圖，給比對用 |
| `icons/*.svg` | 18 個圖示與品牌標誌 |

給人看的兩份 PDF（Design Guideline、Pages）另外提供。Claude Code 也能讀 PDF，但文字檔裡的數值比較精確，所以以這個資料夾為準。
