# RAGcat API 設計 v2

> v2 變更：worker 改成兩個 Lambda（`ingest`、`embed`）；拿掉 edition / draft，embed 完內容直接生效；embed 改用 hash reconcile 判斷變動，不需要版本號和 GC。

## 0. 總覽

### 服務與路由

CloudFront 作為單一網域入口，SPA 與 API 同源（不需要 CORS）。

| Path | 目的地 | Cache |
|---|---|---|
| `/*`（預設） | S3：React SPA | 長快取（檔名帶 hash） |
| `/v1/assistants/*/ask` | ALB → `qa` service | 不快取 |
| `/v1/*` | ALB → `api` service | 不快取 |
| `/internal/*` | 不對外；只在 VPC 內提供給 `discord-bot` | — |

目前 `infra/` 的 CloudFront 使用 VPC origin 連到 private ALB。頁面縮圖在 owner 驗證後由 API 回傳短效 S3 presigned GET URL；原先規劃的 CloudFront `/pages/*` signed URL 尚未實作，因此不建立公開頁面路由。SPA 的 deep links（含 `/auth/callback`）由僅附於預設 behavior 的 CloudFront Function rewrite，不以全站 error fallback 蓋掉 API 的 4xx/5xx。

| Service | 執行環境 | 職責 | 擴縮 |
|---|---|---|---|
| `api` | ECS Fargate | Assistant / Document / Chunk CRUD、publish 開關 | target tracking：ALB request 數 / target，1–2 個 task |
| `qa` | ECS Fargate | 檢索 + 生成，web、HTTP、Discord 共用 | target tracking：ALB request 數 / target，1–4 個 task（I/O bound，不用 CPU 當指標） |
| `ingest` | Lambda（container image） | 解析 PDF、render 頁面縮圖、切 chunk | SQS 觸發，最大並行 5 |
| `embed` | Lambda（同一個 image） | reconcile：embed 有變動的 chunk、刪除向量 | SQS 觸發，最大並行 2（避免 Bedrock 限流） |
| `discord-bot` | ECS Fargate | Discord Gateway 轉接層（P2） | 固定 1 個 task |

A3 的 auto-scaling 與 load distribution 由 ALB + `api` / `qa` 負責；Lambda 的擴縮不算在內。

### 驗證

| 呼叫方 | Header | 權限 |
|---|---|---|
| Owner（web） | `Authorization: Bearer <Cognito access token>`（Google 登入） | 自己擁有的 Assistant；不論是否 published 都能 `ask` |
| 外部 HTTP client | `Authorization: Bearer rk_live_...`（API key） | 只能對綁定的 Assistant 呼叫 `ask`，且 Assistant 必須 published |
| `discord-bot` | `Authorization: Bearer <service token>`（Secrets Manager） | 只能 `ask`，且 Assistant 必須 published |

存取不屬於自己的資源一律回 `404`（不洩漏資源是否存在）。

### 慣例

- JSON、`snake_case`、時間用 ISO 8601 UTC。
- ID 格式為「前綴 + ULID」：`ast_`、`doc_`、`chk_`、`job_`、`key_`。另外有顯示用的 `label`（`AS-01`、`P-14`），建立後就不再變動。
- 分頁：`?limit=50&cursor=...` → `{ "items": [], "next_cursor": null }`。
- 非同步工作回 `202`，前端用 polling 查進度；GET 支援 `ETag` / `If-None-Match` → `304`。
- **樂觀鎖**：所有 chunk 的變更都要帶 `If-Match: "<edit_version>"`。`edit_version` 是 document 層級的計數器，每次變更 +1，只用來防止兩個分頁同時編輯，跟 embed 無關。沒帶回 `428`，不符回 `412`。

### 典型 web 流程

```
1. POST  /v1/assistants                            建立 Assistant
2. POST  /v1/assistants/{id}/documents             取得 presigned upload → 瀏覽器直接 POST 到 S3
   (S3 → EventBridge → SQS parse → ingest Lambda)
3. GET   /v1/documents/{id}                        polling 進度，直到 status=review
4. GET   /v1/documents/{id}/chunks + pages         左邊顯示原文頁面，右邊是 Passages
   PATCH/POST/DELETE chunks                       編輯 / 切分 / 合併 / 新增 / 刪除
5. POST  /v1/documents/{id}/embed                  reconcile → status=ready，內容立即生效
   POST  /v1/assistants/{id}/ask                   在 reading room 測試（owner 不受 published 限制）
6. PATCH /v1/assistants/{id}  { published: true }  開放 Discord 和 API key 發問
```

---

## 1. 資源模型

### User

```json
{
  "id": "cognito-sub",
  "email": "owner@mochipet.example",
  "name": "J",
  "plan": "free",
  "usage": { "period_start": "2026-10-01", "pages_read": 48, "pages_limit": 50, "answers": 12, "answers_limit": 100 },
  "created_at": "..."
}
```

- 只有一種帳號角色：**owner**，只能存取自己的 Assistants。
- **Customer**（在 Discord 發問的人、外部網站的訪客）沒有帳號。系統透過 channel 綁定或 API key 決定他們能問哪個 Assistant，而且只能問 published 的 Assistant。
- 註冊、登入、refresh、登出都在 RAGcat 自己的登入頁完成，api 透過 Cognito API 處理（不跳轉到 Cognito 登入頁，所以沒有 callback URL 和網域設定）。見下方「登入」。
- JIT provisioning：任何 `/v1/*` 請求都會依 JWT 的 `sub` 確保 user 記錄存在（conditional put），所以不需要 Cognito 的 Lambda trigger。登入和註冊時改用 ID token 建立記錄，因為 access token 沒有 email。

### 登入（Cognito 模式；dev 模式這四支回 `404`）

```http
POST /v1/auth/signup    { "email": "...", "password": "..." }   → 201
POST /v1/auth/login     { "email": "...", "password": "..." }   → 200
POST /v1/auth/refresh   { "refresh_token": "..." }              → 200（不回新的 refresh_token）
POST /v1/auth/logout    { "refresh_token": "..." }              → 204
```

```json
{ "access_token": "...", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "...", "user": { "name": "mochi", "email": "mochi@example.com" } }
```

- signup：`AdminCreateUser`（`MessageAction=SUPPRESS`，`email_verified = true`）→ `AdminSetUserPassword`（`Permanent`）→ 登入。完全不寄信，所以沒有驗證頁；不用 `SignUp`，因為它會讓 Cognito 自動寄一封用不到的驗證碼。密碼不符合規則時，刪掉剛建立的帳號，讓使用者能用同一個 email 重試。
- 登入、refresh、撤銷是 Cognito 的公開 API，以不簽章的 client 呼叫，不需要 AWS 憑證；只有建立、確認帳號用 api 的 IAM 角色。app client 開 `USER_PASSWORD_AUTH` 和 `REFRESH_TOKEN_AUTH`；api 的 IAM 多 `AdminCreateUser`、`AdminSetUserPassword`、`AdminDeleteUser`、`AdminConfirmSignUp`、`AdminUpdateUserAttributes`（限這個 pool）。
- login 遇到還沒確認的帳號（例如其他程式用 `SignUp` 註冊到一半），會先確認再登入（密碼要對才會走到這一步）。
- logout 撤銷 refresh token（`RevokeToken`），失敗也不影響前端已經忘掉 token。
- 回應都帶 `Cache-Control: no-store`。錯誤碼給登入頁對應文案：`INVALID_CREDENTIALS`（401）、`EMAIL_EXISTS`（409）、`INVALID_PASSWORD`、`INVALID_INPUT`（400）、`TOO_MANY_ATTEMPTS`（429）、`SESSION_EXPIRED`（401，refresh）、`UPSTREAM_UNAVAILABLE`（503）。
- 前端把 token 存在分頁的 sessionStorage，以 Bearer header 呼叫 API；過期前用 refresh token 換新，同時多個請求只換一次。
- 還沒有忘記密碼：重設碼要靠 email 寄送，目前不保證寄得到，所以先不提供。

### Assistant

```json
{
  "id": "ast_01J9Z...",
  "label": "AS-01",
  "name": "Mochi Pet Co. support",
  "fallback_contact": "help@mochipet.example",
  "status": "live",
  "published": true,
  "document_count": 5,
  "pending_changes": 1,
  "content_version": 23,
  "channels": [{ "platform": "discord", "guild_name": "Mochi Pet Co.", "channel_name": "help-desk" }],
  "created_at": "...",
  "updated_at": "..."
}
```

- `status`：`empty | processing | needs_review | ready | live`（給列表卡片的狀態標籤用）。依序判斷：沒有文件 → `empty`；有文件在 parsing / embedding → `processing`；有 `pending_changes` → `needs_review`；其餘依 `published` 為 `live` 或 `ready`。
- `published`：開放 Discord 和 API key 發問的開關，不影響內容。內容在每次 embed 完成後就生效。
- `content_version`：每次 embed 完成、文件停用或刪除時 +1，只用在 answer cache 的 key（見 §6）。
- `pending_changes`：所有文件 `pending_changes` 的總和。

### Document

```json
{
  "id": "doc_...",
  "assistant_id": "ast_...",
  "filename": "returns-policy.pdf",
  "size_bytes": 8400000,
  "page_count": 24,
  "status": "review",
  "progress": { "stage": "reading_pages", "done": 48, "total": 120, "started_at": "2026-10-08T03:12:40Z" },
  "enabled": true,
  "edit_version": 13,
  "pending_changes": 3,
  "warning_count": 2,
  "error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

`status` 狀態機：

```
awaiting_upload → parsing → review ⇄ embedding → ready
                              ↑                    │
                              └──── 編輯 chunk ─────┘
awaiting_upload | parsing → cancelled
parsing → failed
任何狀態 → deleting
```

- `review`：有尚未 embed 的變更（第一次解析完，或 ready 之後又被編輯）。
- `pending_changes`：需要 reconcile 的 chunk 數，包含已刪除、向量還沒移除的 chunk（見 §5）。
- `enabled=false`：qa 查詢時排除這份文件，立即生效，不需要 embed。
- `error.code`：`NOT_A_PDF | ENCRYPTED_PDF | TOO_MANY_PAGES | NO_TEXT | PARSE_ERROR | QUOTA_EXCEEDED`。

#### 解析進度

`progress` 只在 `parsing` 和 `embedding` 時有值，格式為 `{ stage, done, total, started_at }`。

| RAGcat 步驟 | status · stage | `ingest` 在做什麼 | `done / total` | 可能的錯誤 |
|---|---|---|---|---|
| （上傳） | `awaiting_upload` | 還沒開始；瀏覽器用 XHR upload progress 顯示上傳百分比 | — | — |
| I Checking the file | `parsing` · `checking_file` | 從 S3 下載 PDF，檢查格式、加密、頁數上限、剩餘額度 | — | `NOT_A_PDF`、`ENCRYPTED_PDF`、`TOO_MANY_PAGES`、`PARSE_ERROR`、`QUOTA_EXCEEDED` |
| II Reading pages | `parsing` · `reading_pages` | 逐頁抽出文字區塊和 bbox，render 縮圖上傳 S3，`pages_read + 1` | 已讀頁數 / 總頁數 | `NO_TEXT`（讀完都沒有文字，例如掃描檔） |
| （II 的後段）Describing figures | `parsing` · `describing_figures` | 把有資訊的圖送視覺模型寫成文字描述；文件沒有圖就跳過這段 | 已描述 / 圖片數 | — |
| III Organizing into Passages | `parsing` · `organizing_passages` | 切 passages、算 warnings、批次寫入 DynamoDB | — | — |
| IV Ready to review and test | `review`（`progress = null`） | 完成 | — | — |

- 上傳完成到 `ingest` 開始之間（排隊中），status 仍是 `awaiting_upload`。前端只要上傳成功，就把步驟 I 顯示為進行中。
- `reading_pages` 每 5 頁或每 2 秒寫一次 `progress.done`，取先到者；120 頁大約 24 次寫入。
- 每次寫入都帶條件 `status = parsing`。使用者按 Cancel 後條件會失敗，`ingest` 隨即停止；已讀的頁數仍計入用量（RAGcat 的「Pages already read still count」）。
- 失敗時 status 變成 `failed`，`progress.stage` 停在失敗的那一步，前端據此標出是哪一步失敗。
- 畫面上的 elapsed 由前端用 `started_at` 自己算，伺服器不必持續更新。
- 前端在 `awaiting_upload`、`parsing`、`embedding` 時每 2 秒 polling `GET /v1/documents/{did}`（帶 `If-None-Match`），進入其他狀態就停止。
- Embed 時 `progress = { stage: "embedding", done, total }`，`total` 是這次要 embed 或刪除的 passage 數。

### Chunk（Passage）

```json
{
  "id": "chk_...",
  "label": "P-14",
  "document_id": "doc_...",
  "text": "Opened items cannot be returned unless the item is defective. ...",
  "original_text": "Opened items cannot be returned unless the item is defective ...",
  "origin": "edited",
  "source": {
    "page_start": 3, "page_end": 3, "para_start": 2, "para_end": 2,
    "boxes": [{ "page": 3, "x0": 0.08, "y0": 0.21, "x1": 0.92, "y1": 0.31 }]
  },
  "warnings": [{ "code": "HEADING_ONLY", "message": "Only a heading. Merge it with the next Passage." }],
  "token_count": 42,
  "embedded": false,
  "updated_at": "..."
}
```

- `origin`：`auto | edited | merged | split | added`；`added` 的 `original_text` 為 `null`。
- `boxes` 是相對頁面大小的 0–1 座標，讓前端在任何縮放比例下都能疊在原文頁面上標示。
- `warnings.code`：`HEADING_ONLY | TOO_SHORT | TOO_LONG | TABLE_FRAGMENT`。每次變更後由 `api` 重新計算。
- `embedded`：目前的文字是否已經 embed，也就是 `hash(text) == embedded_hash`。
- 順序由後端用 fractional index 維護，不對外公開；列表一律依文件順序回傳。
- 內部欄位（不對外）：
  - `embedded_hash`：上次 embed 時的內容 hash，沒 embed 過為 `null`。
  - `context`：contextual retrieval 產生的一兩句上下文，由 Indexing 寫入；API 會回傳，Review 畫面以小字顯示。
  - `deleted`：soft delete。刪除和被 merge 掉的 chunk 都只標記，等下次 embed 時才移除向量和資料。列表不回傳 `deleted=true` 的 chunk。

---

## 2. Users 與 Assistants — `api`

| Method | Path | 說明 | 優先 |
|---|---|---|---|
| GET | `/v1/me` | 目前的使用者、方案和用量 | P0 |
| PATCH | `/v1/me` | `{ name }` | P1 |
| DELETE | `/v1/me` | `202`；非同步刪除帳號和所有 Assistants | P2 |
| GET | `/v1/assistants` | 列出我的 Assistants | P0 |
| POST | `/v1/assistants` | `{ name, fallback_contact }` → `201` | P0 |
| GET | `/v1/assistants/{aid}` | 單一 Assistant 詳細資料 | P0 |
| PATCH | `/v1/assistants/{aid}` | `{ name?, fallback_contact?, published? }`；`published` 見 §5 | P0 |
| DELETE | `/v1/assistants/{aid}` | `202`；非同步刪除 S3 檔案與向量 | P1 |

**Quota（P1）**：`ingest` 在步驟 I 先檢查 `pages_read + page_count` 是否超過上限，超過就直接 `failed`（`QUOTA_EXCEEDED`）；步驟 II 每讀一頁用 DynamoDB atomic counter 把 `pages_read + 1`。qa 每次回答都累加 `answers`，超過上限回 `403 QUOTA_EXCEEDED`。

## 3. Documents — `api`

| Method | Path | 說明 | 優先 |
|---|---|---|---|
| GET | `/v1/assistants/{aid}/documents` | 文件列表 | P0 |
| POST | `/v1/assistants/{aid}/documents` | 建立 document 並回傳 presigned upload | P0 |
| GET | `/v1/documents/{did}` | 狀態與進度（polling 用） | P0 |
| PATCH | `/v1/documents/{did}` | `{ enabled }`；立即生效，`content_version + 1` | P1 |
| DELETE | `/v1/documents/{did}` | `202`；status → `deleting`，qa 立即排除；`embed` 移除向量後刪除資料和 S3 檔案 | P0 |
| POST | `/v1/documents/{did}/cancel` | 取消解析；已讀的頁數仍計入用量 | P1 |
| GET | `/v1/documents/{did}/pages?from=1&to=10` | 頁面縮圖 | P0 |
| GET | `/v1/documents/{did}/file` | 原始 PDF 的 signed URL | P1 |
| GET | `/v1/jobs?state=active` | 進行中的工作（右上角「1 task running」） | P1 |

### 上傳

```http
POST /v1/assistants/{aid}/documents
{ "filename": "returns-policy.pdf", "size_bytes": 8400000, "content_type": "application/pdf" }
```

```json
201
{
  "document": { "id": "doc_...", "status": "awaiting_upload", "...": "..." },
  "upload": {
    "method": "POST",
    "url": "https://n12218642-a3-uploads.s3.ap-southeast-2.amazonaws.com",
    "fields": { "key": "uploads/ast_.../doc_....pdf", "Content-Type": "application/pdf", "policy": "...", "x-amz-signature": "..." },
    "expires_at": "..."
  }
}
```

- 用 presigned POST 的 policy 強制 `content-length-range ≤ 50 MB` 和 `Content-Type`；300 頁上限由 `ingest` 檢查。
- 上傳完成後不需要再呼叫 API：S3 ObjectCreated → EventBridge → `parse` queue → `ingest`。

### 頁面

```json
GET /v1/documents/{did}/pages?from=3&to=3
{ "items": [{ "page": 3, "width_pt": 595, "height_pt": 842, "image_url": "https://<cf>/pages/doc_.../3.jpg?Signature=..." }] }
```

---

## 4. Chunks 編輯 — `api`

所有變更都需要帶 `If-Match: "<document.edit_version>"`；document 的 status 為 `parsing` 或 `deleting` 時回 `409 INVALID_STATE`。

Passage 一律掛在 document 底下（`/v1/documents/{did}/chunks/{cid}`）：Document 是 aggregate root，所有編輯都經過它，也剛好對應 DynamoDB 的 partition（`DOC#{did}`），不需要另外用 chunk id 反查 document。

| Method | Path | Body | 優先 |
|---|---|---|---|
| GET | `/v1/documents/{did}/chunks?filter=all\|warnings\|edited\|pending` | — | P0 |
| POST | `/v1/documents/{did}/chunks` | `{ after_id: "chk_..." \| null, text, page? }` 新增 | P0 |
| PATCH | `/v1/documents/{did}/chunks/{cid}` | `{ text }` 編輯 | P0 |
| DELETE | `/v1/documents/{did}/chunks/{cid}` | — 刪除 | P0 |
| POST | `/v1/documents/{did}/chunks/{cid}/split` | `{ parts: ["前半", "後半"] }` | P0 |
| POST | `/v1/documents/{did}/chunks/merge` | `{ ids: ["chk_a", "chk_b"], separator: "\n\n" }` | P0 |
| POST | `/v1/documents/{did}/chunks/{cid}/restore` | — 恢復成 `original_text` | P0 |
| POST | `/v1/documents/{did}/chunks/undo` | — 撤銷上一個操作 | P1 |

**列表回應**

```json
{
  "items": [Chunk],
  "next_cursor": null,
  "edit_version": 13,
  "counts": { "all": 5, "warnings": 2, "edited": 1, "pending": 2, "removed": 1 }
}
```

`counts.removed`：已刪除、下次 embed 時才會移除向量的 chunk 數。

**所有變更都回傳同一種 change set**，前端直接套用到本地狀態：

```json
200  ETag: "14"
{
  "edit_version": 14,
  "upserted": [Chunk],
  "deleted": ["chk_..."],
  "document": { "status": "review", "warning_count": 1, "pending_changes": 3 }
}
```

規則：
- 編輯操作只改內容（`text` 或 `deleted`），不碰任何 embed 相關欄位；要不要重新 embed 由 §5 的 reconcile 判斷。
- **split** 的 body 是切好的 `parts`，不是字元 offset，以避免 JS（UTF-16）和 Python（code point）的 offset 對不上。後端會驗證 `parts` 接起來（忽略切點附近的空白）等於原本的 `text`，不符回 `422 SPLIT_MISMATCH`。第一段保留原 id，其餘建立新 chunk；`boxes` 依字元比例分配。
- **merge** 的 `ids` 必須在文件中相鄰且依序排列，否則回 `422 NOT_CONTIGUOUS`。合併後保留第一個 id，其餘標記 `deleted`；`boxes` 取聯集，`original_text` 串接起來。
- **delete** 只標記 `deleted=true`。
- **restore** 對 `origin=added` 的 chunk 回 `422 CANNOT_RESTORE`。
- 每次變更會讓 `edit_version + 1`，並把 document 退回 `review`。document 正在 `embedding` 時仍允許編輯，變更不會遺失（見 §5）。
- 每次變更都寫入 op log（存 inverse operation），供 undo 使用。undo 一個刪除就是把 `deleted` 改回 `false`。

---

## 5. Embed（reconcile）與 Publish

### Embed — `api`

```http
POST /v1/documents/{did}/embed
```

```json
202
{ "job": { "id": "job_...", "type": "reconcile", "document_id": "doc_..." }, "document": { "status": "embedding" } }
```

- `pending_changes = 0` 時回 `409 NO_CHANGES`。
- api 用 conditional update 把 status 切到 `embedding`，所以同一份文件同時只會有一個 job；已經在 embedding 時回傳既有的 job。

### Reconcile 規則 — `embed` Lambda

讀出整份文件的 chunk（一次 Query 同一個 partition），逐筆比對：

```
want = (chunk.deleted || document.status == deleting) ? null
     : sha256(EMBED_MODEL + (contextual ? CONTEXT_PROMPT_VERSION + section : "") + text)
section = 依文件順序，這個 passage 之前最近的標題（shared/kernel.py 的 sections）
have = chunk.embedded_hash
```

| want vs have | 動作 |
|---|---|
| 相等 | 不做事 |
| want 有值、和 have 不同 | embed → `PutVectors`（key = `chk_id`，直接覆寫）→ 寫 `embedded_hash = want` |
| want 為 null、have 有值 | `DeleteVectors` → 刪除 chunk（條件：`deleted = true`） |
| 兩者都是 null | 直接刪除 chunk（新增後還沒 embed 就被刪掉的） |

- 順序：先處理所有刪除，再處理寫入。
- `embedded_hash` 一律在 `PutVectors` 成功之後才寫。
- 結束時：
  - 重新計算 `pending_changes`：為 0 → `ready`；大於 0（期間又被編輯）→ `review`。
  - assistant 的 `content_version + 1`。
  - document 是 `deleting` 時，接著刪除 document 記錄和 S3 上的 PDF、頁面縮圖。

這個做法的性質：
- **編輯不會遺失**：寫入的是讀取當下那段文字的 hash；embed 期間被改過的 chunk，下次比對時 hash 不相等，仍然是 pending。
- **可重試**：job 是 idempotent，SQS 重送或中途失敗重跑，結果都一樣。
- **改回原文不會重新 embed**：restore 或 undo 之後 hash 和 `embedded_hash` 相同，直接略過。
- **換 embedding model 會自動全部重做**：hash 含 model id；開關 contextual 或改 context prompt 的版本也一樣。
- **改章節標題時，連帶重做該章節的段落**：開啟 contextual 時 hash 含 section，Review 畫面會顯示這些段落為「not embedded」。

### Contextual retrieval（`RAGCAT_CONTEXTUAL=on`，預設開啟）

- 對每個要寫入的 passage 呼叫 LLM 一次（`max_tokens` 1000），輸入是文件標題、section 和本文，要求回 JSON：一兩句上下文 `context`，加上 passage 提到的實體 `entities`（`{name, type}`）。同時處理 4 段，遇到 throttling 時以 adaptive retry 退避重試。
- 實體類型是固定清單（`indexing/domain.py` 的 `ENTITY_TYPES`：product、policy、condition、fee、period、contact、organization、person、location）。不在清單內的類型、重複的實體會被丟掉，每段最多 10 個。改清單或 prompt 要同步調高 `CONTEXT_PROMPT_VERSION`，所有文件會重新 embed。
- 向量的輸入改為 `context + "\nEntities: name (type), …" + "\n\n" + text`（沒有實體就省略 Entities 那行）。`context` 和 `section` 會寫回 passage，`context`、`entities` 另存進向量 metadata。
- 回覆不是合格的 JSON 時不讓文件失敗：記 warning，該段改用沒有上下文的本文 embed。
- 回答時檢索流程不變。prompt 只多加 section 作為來源標頭，引用顯示的仍是原文。
- 模型無法使用時，文件回到 `review`，錯誤碼為 `error.code = EMBED_FAILED`。已完成的段落會保留，再按一次 embed 就從中斷處繼續。

**向量格式**（S3 Vectors，index 為 1024 維、cosine）
- key：`chk_id`。
- filterable metadata：`assistant_id`、`document_id`、`embedding_key`，以及 `entities`（字串清單，格式 `type:name`，沒有實體時不寫這個欄位；不在 non-filterable 清單，所以日後可直接拿來過濾）。
- non-filterable metadata（建 index 時宣告）：`text`、`section`、`context`、`label`、`document_title`、`page`、`para`、`boxes`、`edited`。

### Publish

```http
PATCH /v1/assistants/{aid}
{ "published": true }
```

- 只是開關，決定 Discord 和 API key 能不能發問，不涉及內容版本。
- 開啟時至少要有一份 `ready` 的文件，否則回 `409 INVALID_STATE`。
- 上線後的修改，embed 完就直接生效。要在發布前測試修改，用 ask 的 `preview`：只有 owner 看得到，不寫入向量庫，也沒有另一份 draft 索引。

---

## 6. 問答 — `qa`

```http
POST /v1/assistants/{aid}/ask
Accept: text/event-stream
{ "question": "Can I return an opened bag of kibble?", "stream": true, "preview": false }
```

- Owner 一律可以問；API key 和 `discord-bot` 問未 published 的 Assistant 會回 `403 NOT_PUBLISHED`。
- `preview: true`（只限 owner，Test 用）：還沒發布的修改也參與回答，客人看到的不受影響。做法見下方「預覽」。
- `stream: false` → 回一次性的 JSON（給 Discord bot 和一般 HTTP client 用）。

**SSE**

```
event: meta
data: {"request_id":"req_...","content_version":23,"cached":false,"preview":false}

event: preparing
data: {"done":16,"total":20}

event: token
data: {"text":"Only if the product is defective."}

event: citations
data: {"items":[{"n":1,"chunk_id":"chk_...","label":"P-14","document_id":"doc_...","document_title":"returns-policy.pdf","page":3,"para":2,"boxes":[...],"edited":true}]}

event: done
data: {"answered":true,"fallback":null,"usage":{"input_tokens":812,"output_tokens":41},"latency_ms":1840}
```

**JSON（`stream: false`）**

```json
{
  "request_id": "req_...",
  "answer": "Only if the product is defective. [1]",
  "answered": true,
  "citations": [{ "n": 1, "...": "..." }],
  "fallback": null,
  "content_version": 23,
  "cached": false,
  "preview": false
}
```

- 最多 3 個引用；`edited: true` 對應 RAGcat 的「as edited by you」。
- 找不到答案時：`answered: false`，`fallback: { "contact": "help@mochipet.example", "message": "..." }`。
- 錯誤：串流進行中出錯時送 `event: error` `{code, message}`；Bedrock 被限流時回 `503 UPSTREAM_UNAVAILABLE` + `Retry-After`。
- Rate limit：以 API key 或 Assistant 為單位，在 Valkey 做 token bucket，超過回 `429` + `Retry-After`。

**內部處理（不影響 API 介面，列出供實作參考）**
1. Assistant config：`published`、`content_version`、要排除的 document id（停用或刪除中）。採 cache-aside，key 為 `ast:{aid}`；api 在相關寫入後刪除這個 key。
2. Answer cache：`ans:{aid}:{content_version}:{sha256(normalized question)}`，TTL 24 小時。embed 完 `content_version` 改變，舊 key 自然不會再被讀到。
3. Query embedding cache：`qemb:{sha256(question)}`。
4. S3 Vectors `QueryVectors`：filter `assistant_id = aid`，且 `document_id` 不在排除清單（`$nin`），topK = 5。
5. 引用所需的 chunk 文字、頁碼和 bbox 都存在向量的 metadata，查詢時不必再讀 DynamoDB。

**預覽（`preview: true`）**
- 跟 reconcile 用同一套 hash 比對，找出 Assistant 底下有變動的段落。只看 `review`、`embedding`、`ready` 而且開啟、沒被排除的文件。
- 失效的 key：線上向量已不符合段落的，包括改過的段落、拆分後沿用原 id 的第一段、因標題變動連帶改變 section 的段落，以及刪除的段落。
- 檢索：線上索引取 `5 + 失效數` 筆（最多 100 筆，一頁 `QueryVectors`），剔除失效的 key，再加上預覽段落（在記憶體算 cosine），排序後取前 5。
- 預覽段落的上下文和向量存在 Valkey：key 為 `pv:{chk_id}:{hash}`，TTL 7 天，不寫入向量庫。之後再問直接取用；Publish 的 reconcile 也先查這個 key，有就直接寫入，不再呼叫 LLM 和 embedding，上線的就是測過的那份。
- 準備時送 `event: preparing {done, total}`（每 16 段一次）。一次要準備的段落超過 100 段時回 `409 TOO_MANY_CHANGES`，`details: {passages, limit}`。
- 預覽答案不寫 answer cache。沒有未發布的變更時，等同一般提問（可以走 cache）。

---

## 7. Discord 整合 — `api` + `discord-bot`（P2）

| Method | Path | 說明 |
|---|---|---|
| GET | `/v1/integrations/discord/install?assistant_id=` | 回傳 bot 的 OAuth2 安裝 URL（`state` 帶簽章） |
| GET | `/v1/integrations/discord/callback` | OAuth 完成後記錄 guild，再 redirect 回 web |
| GET | `/v1/integrations/discord/guilds/{gid}/channels` | 列出頻道，含 `assigned_assistant_id` |
| PUT | `/v1/assistants/{aid}/channels` | `{ discord_channel_ids: [...] }`；頻道已被其他 Assistant 佔用時回 `409 CHANNEL_IN_USE` |
| GET | `/internal/v1/discord/channels/{channel_id}` | bot 查詢 channel 對應的 assistant（只限 VPC 內） |

Bot 流程：收到 @mention → 查 channel 綁定（在記憶體 cache 60 秒）→ 呼叫 `qa` 的 `ask`（`stream:false`）→ 把引用排成註腳回覆。

## 8. API Keys — `api`（P1）

| Method | Path | 說明 |
|---|---|---|
| POST | `/v1/assistants/{aid}/api-keys` | `{ name }` → `{ id, key, prefix }`，`key` 只會顯示這一次 |
| GET | `/v1/assistants/{aid}/api-keys` | 列表（只顯示 prefix） |
| DELETE | `/v1/api-keys/{kid}` | 撤銷 |

只儲存 key 的 hash；權限限定該 Assistant 的 `ask`，且 Assistant 必須 published。

---

## 9. 內部訊息（SQS → Lambda）

| Queue | 生產者 | 消費者 | 訊息 |
|---|---|---|---|
| `parse` | EventBridge（S3 ObjectCreated） | `ingest` | 原始的 S3 event；從 object key 取出 `doc_id` |
| `embed` | `api` | `embed` | `{ "type": "reconcile", "job_id", "document_id" }` |

- 兩個 Lambda 共用同一個 ARM64 container image（`backend/Dockerfile` 的 `worker` target），用 `image_config.command` 指定 handler：`ragcat.apps.worker.ingest`、`ragcat.apps.worker.embed`。
- 由 event source mapping 觸發：batch size 1，maximum concurrency `ingest` 5、`embed` 2。
- 資源：`ingest` 3 GB / 10 分鐘，`embed` 1 GB / 10 分鐘。queue 的 visibility timeout 設為 function timeout 的 6 倍（AWS 建議值）。
- 兩個 queue 都有 DLQ（`maxReceiveCount=3`）。
- Idempotency：`ingest` 用 conditional write 把 status 從 `awaiting_upload` 切到 `parsing`，重送的訊息會被略過；`embed` 的 reconcile 本身就是 idempotent。

## 10. 錯誤格式

```json
{ "error": { "code": "PRECONDITION_FAILED", "message": "Document has changed", "details": { "current_edit_version": 15 } } }
```

| HTTP | code |
|---|---|
| 400 | `VALIDATION_ERROR` |
| 401 | `UNAUTHENTICATED` |
| 403 | `FORBIDDEN`、`QUOTA_EXCEEDED`、`NOT_PUBLISHED` |
| 404 | `NOT_FOUND` |
| 409 | `INVALID_STATE`、`NO_CHANGES`、`CHANNEL_IN_USE` |
| 412 | `PRECONDITION_FAILED` |
| 422 | `SPLIT_MISMATCH`、`NOT_CONTIGUOUS`、`CANNOT_RESTORE` |
| 428 | `PRECONDITION_REQUIRED` |
| 429 | `RATE_LIMITED` |
| 503 | `UPSTREAM_UNAVAILABLE` |

---

## 11. 實作優先順序

- **P0（web MVP）**：`GET /v1/me`、Assistants CRUD、上傳與進度、頁面縮圖、chunk 編輯（list/add/edit/delete/split/merge/restore）、刪除文件、embed（reconcile）、publish 開關、`ask`（SSE）
- **P1**：jobs、undo、enabled 開關、刪除 Assistant、API keys、rate limit、quota
- **P2**：Discord、未回答問題紀錄（Questions 分頁）
