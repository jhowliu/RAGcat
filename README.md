# RAGcat (CAB432 A3)

上傳 PDF → 切成 passages → owner 審閱、編輯 → embed → 附引用的 RAG 問答。

- 設計文件：[`docs/api-design.md`](docs/api-design.md)（API）、[`docs/domain-design.md`](docs/domain-design.md)（DDD、程式結構）
- `backend/`：Python 3.12+、FastAPI、PyMuPDF、boto3
- `web/`：React + Vite + TypeScript。視覺依 [`DESIGN.md`](DESIGN.md)（2026-10 改版；數值只來自 `web/src/theme/tokens.css`，吉祥物圖在 `web/public/cat/`）；流程、文案、狀態與無障礙仍依 [`designs/`](designs/)（H3）；中英雙語字典在 `web/src/locales/`

## 介面與後端的對應

- **Publish changes**：把有變動的文件做 embed，第一次發布時再打開 Assistant 的 `published`。客人只看得到已經 embed 的段落，所以沒按 Publish changes 之前，修改不會被客人看到。
- **Test**（Review & test 頁）：一律用最新的修改。Assistant 尚未發布時，提問前會先發布有變動的文件（此時只有 owner 能問）。已經上線後改用預覽：只對 owner，把有變動的段落當場算出上下文和向量（暫存在 Valkey，不寫入向量庫），和線上段落一起檢索；客人看到的仍是已發布的版本。之後按 Publish changes 會直接寫入預覽算好的向量，不再重算。一次要準備超過 100 段時會請你先發布。
- 設計稿裡 backend 還不支援的部分先不顯示：Discord 連接（Channels）、Questions、Billing、Version history、通知、Undo、重複檔偵測。

## 本機開發

需要 Docker、[uv](https://docs.astral.sh/uv/) 和 Node 22.16+。

```bash
make deps      # 啟動 DynamoDB Local（:8001）和 Valkey（:6380），安裝 backend 和 web 的套件
cp -n .env.local.example .env.local  # 首次設定；不覆蓋既有檔案
# 在 .env.local 填入 ANTHROPIC_API_KEY 和 OPENAI_API_KEY
make backend   # :8010；api + qa，parse/embed 工作送進 Valkey queue（自動 reload）
make worker    # 另開一個 terminal：消費 queue，做 parse 和 embed（不會自動 reload，改程式後要重啟）
make web       # http://localhost:5173，/v1 和 /dev proxy 到 :8010
```

`.env.local` 只在後端載入，不可提交或放入 `VITE_*` 前端環境變數。缺少 API key 時後端 app 會明確報錯，不會偷偷改用假模型。啟動 log 會顯示實際 QA、embedding 和 vision provider，沒有 API key。
改動 API key、preset 或 model 設定後，要停止並重新執行 `make backend`；既有服務的啟動環境不會因修改 Makefile 或 env 檔自動更新。

打開 http://localhost:5173 ，建立 Assistant，上傳 `samples/` 裡的範例：`mochi-returns-policy.pdf`（英文、表格）或 `mochi-care-guide-zh.pdf`（中文、雙欄、表格）。重新產生範例：`cd backend && uv run python ../samples/make_samples.py`。

`make backend` 不需要 AWS，但會呼叫付費模型 API。只要離線驗證流程，可改用 `make backend-offline`：QA、embedding 和 vision 都明確使用 fakes，也不載入 `.env.local`。直接執行 uvicorn、沒有設定 model preset 時仍預設 fake，讓離線測試不會意外產生費用。

儲存和 queue 留在本機，模型 provider 可獨立選擇：

| Port | 本機（`make backend`） | AWS | 環境變數 |
|---|---|---|---|
| Table | DynamoDB Local | DynamoDB | `RAGCAT_DYNAMODB_ENDPOINT`、`RAGCAT_TABLE` |
| Object store | `.data/objects` + `/dev/s3/upload` | S3 presigned POST | `RAGCAT_STORAGE=local\|s3` |
| Queue | Valkey list + `make worker`（重試 3 次，失敗進 `queue:<name>:dlq`）；`backend-offline` 用背景 thread | SQS → Lambda | `RAGCAT_QUEUE=local\|redis\|sqs`、`RAGCAT_QUEUE_URL` |
| Vector index | `.data/vectors.json` | S3 Vectors | `RAGCAT_VECTORS=local\|s3vectors` |
| QA / context | Claude Messages（`claude-haiku-5-5`） | Bedrock Converse（Gemma，既有預設） | `RAGCAT_LLM_PROVIDER=fake\|claude\|bedrock`、`RAGCAT_LLM_MODEL_ID` |
| Embedding | OpenAI `text-embedding-3-small`，1536 維 | Bedrock Titan v2，1024 維 | `RAGCAT_EMBED_PROVIDER=fake\|openai\|bedrock`、`RAGCAT_EMBED_MODEL_ID`、`RAGCAT_EMBED_DIMS` |
| Vision | fake 圖片描述（這次未改成 Claude） | Bedrock Converse | `RAGCAT_VISION_PROVIDER=fake\|bedrock` |
| Cache | process 內 dict | ElastiCache Valkey | `RAGCAT_CACHE=memory\|valkey` |
| Auth | `Bearer dev:<name>` | Cognito JWT | `RAGCAT_AUTH=dev\|cognito` |
| Contextual retrieval | 開（Claude 依章節產生上下文） | 開（Bedrock LLM） | `RAGCAT_CONTEXTUAL=on\|off` |

`RAGCAT_MODELS` 是簡便 preset：`local` 選 Claude/OpenAI/fake vision，`bedrock` 三者全走 Bedrock，`fake` 三者全離線；各 provider 的環境變數可覆蓋 preset。QA 的 `stream/complete` 和 embedding 的 `embed` 介面不變，Indexing 與 Answering 使用同一個 embedding adapter。

OpenAI adapter 依[官方 OpenAI documentation](https://developers.openai.com/api/reference/resources/embeddings/methods/create)呼叫 `/v1/embeddings`，批次向量依 response index 排回輸入順序，檢查維度與數值。Claude adapter 依[官方 Messages/streaming 文件](https://platform.claude.com/docs/en/build-with-claude/streaming)處理 SSE、usage、context completion 和中途錯誤。預設 Haiku 5.5 關閉 thinking，避免 120-token context / 400-token QA 預算被 thinking 耗盡；[官方說明](https://platform.claude.com/docs/en/models/haiku-5-5/whats-new-haiku-5-5)。其他 Claude model 可用 `RAGCAT_LLM_MODEL_ID` 切換，但其 thinking 規則與小 output budget 需另外驗證。

Contextual retrieval 會額外對每個待更新 passage 呼叫 Claude，QA 也另行計費。OpenAI embedding 費只涵蓋向量化，不含這兩項。正式線上的 Terraform 明確選擇 Bedrock，不使用本機 `.env.local` 或 OpenAI/Anthropic API keys。

切換 provider/model/dimensions 後，先按 **Publish changes** 重新 embed 舊文件；draft Assistant 的 **Test** 也會先 embed pending changes。向量 metadata 記錄 embedding space，檢索不會混用舊 hashing 向量或不同維度。舊索引缺少 space 標記時不納入檢索，但不會自動刪除。QA/context model 變更也會更新相關 hash/cache namespace，避免拿到前一個模型的答案。

本機若要 QA 和 embedding 都改走 Bedrock，可不用 `.env.local` 直接執行：

```bash
aws sso login --profile diana
cd backend && AWS_PROFILE=diana RAGCAT_MODELS=bedrock \
  RAGCAT_LLM_PROVIDER=bedrock RAGCAT_EMBED_PROVIDER=bedrock RAGCAT_VISION_PROVIDER=bedrock \
  RAGCAT_DYNAMODB_ENDPOINT=http://localhost:8001 RAGCAT_DATA_DIR=$PWD/../.data \
  uv run uvicorn ragcat.apps.dev:app --port 8010 --reload --reload-dir src
```

上傳、儲存、背景 worker 和 auth 仍為本機實作；這個命令只將模型改為 Bedrock。

## 測試

```bash
make test   # backend：單元/JWT/HTTP 整合測試；web：登入測試與型別檢查
make test-integration # DynamoDB 無法連線時會失敗，不會默默 skip
```

## Container images

```bash
make images   # ragcat-service:dev 和 ragcat-worker:dev（linux/arm64）
```

| Image | 用途 | 選擇進入點 |
|---|---|---|
| `ragcat-service` | ECS：`api`、`qa`（port 8080，health check `/healthz`） | task definition 的 `command`：預設 `uvicorn ragcat.apps.api:app`，qa 改成 `["uvicorn", "ragcat.apps.qa:app"]` |
| `ragcat-worker` | Lambda：`ingest`、`embed` | `image_config.command`：`ragcat.apps.worker.ingest` / `ragcat.apps.worker.embed` |

兩個 image 都依 `uv.lock` 安裝套件。沒設定的 `RAGCAT_*` 都是本機預設值，部署時要設成 AWS 的值（`RAGCAT_STORAGE=s3` 等）。

本機跑 worker image（內建 Lambda Runtime Interface Emulator）：

```bash
docker run --rm -p 9000:8080 -e RAGCAT_DYNAMODB_ENDPOINT=http://host.docker.internal:8001 \
  ragcat-worker:dev ragcat.apps.worker.embed
curl -X POST localhost:9000/2015-03-31/functions/function/invocations \
  -d '{"Records":[{"body":"{\"document_id\":\"doc_x\"}"}]}'
```

## 尚未完成

- AWS 實際部署與驗證：[`infra/README.md`](infra/README.md) 已提供 Terraform、bootstrap/image/web 發布流程、CloudWatch、smoke/load test 與 submission YAML 匯出；尚未 apply，亦未在 AWS 驗證。
- Cognito 正式登入的 live 驗證：RAGcat 自己的登入頁（email + 密碼）經由 `/v1/auth/*` 呼叫 Cognito API，註冊時由後端直接建立已確認的帳號、完全不寄信；refresh/logout 都已實作並有單元測試，仍需完成雲端 sign-in smoke test。
- P1：undo、API keys、rate limit；P2：Discord
