# Local storage/queue/cache; Claude QA + OpenAI embeddings by default. See README for API keys.
LOCAL_ENV = RAGCAT_DYNAMODB_ENDPOINT=http://localhost:8001 RAGCAT_DATA_DIR=$(CURDIR)/.data
LOCAL_ENV_FILE = $(if $(wildcard $(CURDIR)/.env.local),--env-file $(CURDIR)/.env.local,)
UV_CACHE_DIR ?= $(CURDIR)/.data/uv-cache
export UV_CACHE_DIR
AWS_PROFILE ?= diana

.PHONY: deps backend worker backend-offline web test test-integration build images cloud-audit infra-init infra-validate infra-plan infra-apply cloud-images cloud-web cloud-submission clean-data

deps:
	docker compose up -d dynamodb valkey
	cd backend && uv sync
	cd web && npm install

backend: ## api + qa on :8010, sending parse/embed jobs to Valkey; run `make worker` too
	docker compose up -d dynamodb valkey
	cd backend && $(LOCAL_ENV) RAGCAT_QUEUE=redis RAGCAT_CACHE=valkey RAGCAT_MODELS=local uv run uvicorn ragcat.apps.dev:app --port 8010 --reload --reload-dir src $(LOCAL_ENV_FILE)

worker: ## consumes the parse/embed queues with the same models as `make backend`; no reload, restart after code changes
	docker compose up -d dynamodb valkey
	cd backend && $(LOCAL_ENV) RAGCAT_QUEUE=redis RAGCAT_CACHE=valkey RAGCAT_MODELS=local uv run $(LOCAL_ENV_FILE) python -m ragcat.apps.worker

backend-offline: ## one process (worker on a thread); explicit fake QA/embedding/vision, no paid model APIs or env file
	docker compose up -d dynamodb
	cd backend && $(LOCAL_ENV) RAGCAT_MODELS=fake RAGCAT_LLM_PROVIDER=fake RAGCAT_EMBED_PROVIDER=fake RAGCAT_VISION_PROVIDER=fake uv run uvicorn ragcat.apps.dev:app --port 8010 --reload --reload-dir src

web: ## Vite on :5173, proxying /v1 and /dev to :8010
	cd web && npm run dev

test:
	cd backend && uv run pytest -q
	cd web && npm run test
	cd web && npm run typecheck

test-integration: ## Never reports a green integration run by silently skipping DynamoDB tests.
	cd backend && uv run pytest -q tests/test_flow.py --require-integration

build:
	cd web && npm run build

# arm64 for Fargate (Graviton) and Lambda. --provenance=false: Lambda rejects the image index
# that buildx creates when it attaches provenance attestations.
images: ## ragcat-service (api, qa) and ragcat-worker (ingest, embed Lambdas)
	cd backend && docker buildx build --platform linux/arm64 --provenance=false --target service -t ragcat-service:dev --load .
	cd backend && docker buildx build --platform linux/arm64 --provenance=false --target worker -t ragcat-worker:dev --load .

cloud-audit:
	cd backend && uv run python ../scripts/aws_inventory.py --profile $(AWS_PROFILE) --output ../infra/inventory.json

infra-init:
	terraform -chdir=infra init

infra-validate:
	terraform -chdir=infra fmt -check
	terraform -chdir=infra validate

# Terraform can't refresh this SSO profile's token itself; hand it the CLI's short-lived credentials.
TF_AWS = creds="$$(aws configure export-credentials --profile $(AWS_PROFILE) --format env)" && eval "$$creds" && AWS_REGION=ap-southeast-2

infra-plan:
	$(TF_AWS) terraform -chdir=infra plan -input=false -out=stack.tfplan

infra-apply: ## Applies only the saved plan produced by infra-plan.
	$(TF_AWS) terraform -chdir=infra apply stack.tfplan

cloud-images:
	cd backend && uv run python ../scripts/deploy.py images --profile $(AWS_PROFILE) --tag "$(IMAGE_TAG)"

cloud-web:
	cd backend && uv run python ../scripts/deploy.py web --profile $(AWS_PROFILE)

cloud-submission:
	cd backend && uv run python ../scripts/deploy.py submission

clean-data: ## wipe local uploads, page images and vectors (DynamoDB Local keeps its own volume)
	rm -rf .data
