# AWS deployment

This directory defines the RAGcat P0 deployment. It has **not been applied**. The current agent environment cannot access the Docker daemon or AWS SSO endpoints, and Terraform is not installed. Provider initialization, `terraform validate`, the AWS inventory and cloud smoke/load tests still need to run in an environment with those prerequisites. The source was checked against the AWS provider documentation; that is not a substitute for Terraform validation.

## Prerequisites and existing resources

- Terraform 1.12+, AWS provider 6.25+ (below 7), Docker with buildx, Node 22.16+, and the backend Python environment.
- AWS profile `diana` authenticated to the CAB432 account in `ap-southeast-2`.
- Your verified QUT email for `qut-username` tags; names default to the existing code's `n12218642` prefix.
- The existing Cognito User Pool ID. The shared pool is not managed by this stack; Terraform only adds RAGcat's own app client (password and refresh-token sign-in, no hosted login page, no callback URLs).
- Confirm model invocation permissions for `amazon.titan-embed-text-v2:0` and `google.gemma-3-12b-it`. Seeing models in the catalog does not prove permission to invoke them.
- Cloud runtimes explicitly select the Bedrock QA, embedding and vision adapters. Local `make backend` instead uses Claude QA/context and OpenAI `text-embedding-3-small` (see the root `.env.local.example`); no local API keys are deployed. Keep query/index embedding models identical, and re-embed documents after a model change.
- Optional verified ECS cluster ARN and an existing VPC/subnet set. A reused network needs an attached internet gateway, private-subnet outbound access, and subnets in two AZs. A reused ECS cluster needs Container Insights enabled for task-count dashboard metrics; otherwise inspect task counts through ECS scaling activities.

First run:

```sh
docker compose up -d dynamodb
make test-integration
make test
make build
aws sso login --profile diana
make cloud-audit
```

`cloud-audit` only reads account metadata and writes `infra/inventory.json`. It does not create resources or print credentials. AccessDenied checks are reported separately; a successful catalog/list call does not certify all create/update permissions. Review the existing resources before deciding whether to reuse the network and cluster.

Copy `terraform.tfvars.example` to `terraform.tfvars` and replace its placeholders with verified values. The state and tfvars are ignored by Git. Keep the Terraform state: losing it would prevent safe updates to already-created resources. Before multi-user use, configure an approved remote state backend with locking; the initial stack uses local state to avoid assuming ownership of an existing shared bucket.

## Bootstrap and workload deployment

The image repositories must exist before the container images can be pushed. `deploy_workloads = false` creates the infrastructure and authentication client without ECS tasks or Lambda functions. This bootstrap **already provisions** the ALB, NAT gateway, cache, and other resources with ongoing costs.

```sh
make infra-init
terraform -chdir=infra fmt
make infra-validate
make infra-plan
make infra-apply
make cloud-images IMAGE_TAG=release-20261014-1
```

Review the saved plan before `infra-apply`. Do not import or rename shared resources into this stack: reuse the User Pool and optional cluster/network through variables. If IAM denies creation of the CloudFront VPC-origin service-linked role or other required resources, resolve that specific account permission with the teaching team instead of opening the ALB publicly.

After both images are pushed, set:

```hcl
deploy_workloads = true
image_tag       = "release-20261014-1"
```

Then:

```sh
make infra-plan
make infra-apply
make cloud-web
terraform -chdir=infra output -raw site_url
```

Image tags are immutable; each release uses a new tag. Terraform resolves the tag to a digest and pins both ECS and Lambda to that digest. `cloud-web` builds and uploads the SPA and invalidates CloudFront. It preserves older static assets rather than deleting potentially active files. The browser holds no AWS secrets and no Cognito settings: it only talks to the API.

Open the site, create an account on RAGcat's own sign-in page, and verify the requested page opens once signed in. Production never falls back to a development token. `/v1/auth/*` signs in through the Cognito API; sign-up creates a confirmed account itself and sends no email. Access tokens are refreshed through `/v1/auth/refresh`, sign-out revokes the refresh token and returns to `/`, and tokens remain in the tab's session storage. The backend verifies RSA signatures, issuer, expiry, required claims, and the app-specific token audience/client ID.

## Routing and persistence

| Flow | Resources and behavior |
|---|---|
| SPA and deep links | Private web S3 bucket → CloudFront OAC; a viewer-request function rewrites SPA paths to `index.html`. |
| Management | `/v1/*` → CloudFront VPC origin → internal ALB → `api` ECS service. |
| Questions | ALB rule `/v1/assistants/*/ask` and `/v1/widget/*/ask` (Website widget) takes priority and targets the separate `qa` service. API caching and response compression are disabled for SSE. The api reads the built `widget.html` from `RAGCAT_WIDGET_TEMPLATE_URL` (the CloudFront domain) to serve `/v1/widget/{aid}/frame`. |
| Upload | Browser posts directly to the private files S3 bucket using a presigned POST; bucket CORS permits the site origin. |
| Parse | Files bucket EventBridge events for `uploads/` → parse SQS → ingest Lambda. Generated `pages/` objects cannot retrigger ingestion. |
| Publish/delete | API sends embed SQS messages → embed Lambda reconciles S3 Vectors and document state. |
| Page preview | Backend returns an expiring S3 presigned GET URL after checking ownership. No public CloudFront `/pages/*` route exposes the private thumbnails. |
| Application data | One on-demand DynamoDB table with PK/SK and GSI1. |
| Retrieval | S3 Vectors cosine index matches Titan's configured dimensions. Assistant/Document IDs and `embedding_key` are filterable; large text and citation fields are non-filterable metadata. Queries never mix different embedding spaces. |
| Cache | TLS Valkey shared by API, QA, and workers preserves cross-process config invalidation, cached query vectors and versioned answer keys. |

All runtimes run in private subnets. For a new VPC there is one NAT gateway, used for AWS APIs, image pulls and Cognito JWKS. This reduces gateway count but makes outbound access depend on one AZ. Valkey uses one small primary and no replica: a cache failure falls back to cache misses, although requests may slow down. These are assessment-scale cost/availability tradeoffs to measure and explain.

API tasks scale from 1–2 and QA tasks from 1–4 using `ALBRequestCountPerTarget`; initial targets are 300 and 60 requests per task per minute, respectively. Tune them from observed service capacity. Desired task count is excluded from Terraform drift correction so applying a deployment does not undo auto-scaling.

Lambda SQS mappings cap concurrency at 5 ingest and 2 embed, with batch size 1. Function timeout is 900 seconds and queue visibility is 5400 seconds. DLQs retain failures after three receives. Reserved Lambda concurrency is not allocated automatically in the shared account.

## Smoke test and evidence

Set `RAGCAT_ACCESS_TOKEN` in your terminal to a current Cognito **access** token without committing or displaying it. Scripts take the credential from the environment and never print it. For local-only testing, `smoke_cloud.py` also accepts `dev:<name>` when the origin is localhost.

```sh
cd backend
uv run python ../scripts/smoke_cloud.py --base-url https://YOUR_DISTRIBUTION.cloudfront.net --keep
```

The smoke test creates a marked Assistant and Document, waits for parsing, loads a signed page image, edits a Passage with `If-Match`, embeds, publishes, and checks two SSE answers: a cold result with citations followed by a cache hit. S3 requests use a separate client without the owner's Authorization header. `--keep` retains the demonstration Document; without it, only the test's newly uploaded Document is deleted. The empty test Assistant remains because the current API does not support deleting Assistants. Reuse its printed ID with `--assistant-id` on subsequent runs.

For scaling evidence:

```sh
# API traffic: no per-request model invocations.
uv run python ../scripts/load_cloud.py --base-url https://YOUR_DISTRIBUTION.cloudfront.net --seconds 300 --requests-per-second 10

# QA traffic: use the smoke-test Assistant. Warmup proves that answers are cached first.
uv run python ../scripts/load_cloud.py --base-url https://YOUR_DISTRIBUTION.cloudfront.net --assistant-id ast_YOUR_SMOKE_ASSISTANT --seconds 300 --requests-per-second 5
```

The load tool bounds concurrency, duration and rate. QA load stops if a response stops hitting the cache, to prevent unexpected repeated model calls. It also stops on expired/forbidden credentials. A completed request loop does **not** establish that scaling occurred: record ECS scaling activities and task counts, ALB per-target requests, latency/error rates, then wait for and capture scale-in after traffic stops. Repeat with a justified target/load only if the first run did not trigger the intended policy.

The CloudWatch dashboard includes ECS CPU/task counts, ALB requests per target, cache hits/misses, answer latency and queue backlog. QA completion logs are JSON with no question, answer text, or authentication token; metric filters derive cache and latency metrics. Alarms flag DLQs, Lambda errors and unhealthy targets. Capture parsing/publishing progress and the queue/worker interaction for asynchronous evidence. Lambda's built-in scaling does not fulfill the assignment's auto-scaling requirement.

Once the applied deployment is verified:

```sh
make cloud-submission
```

This exports the applied Terraform resource identifiers to `infra/submission-a3-infra.yml` and refuses a bootstrap-only stack. Some AWS child/global resources do not support ownership tags; verify the assignment's handling of those and reused resources against the provided submission template. Prepare the report, architecture diagrams, Pricing Calculator estimate and 4–5 minute demonstration using measurements from the actual deployment. The assignment requires you to draft the report yourself.

## Checks completed in this session

- Backend tests: 55 passed; five DynamoDB HTTP integration tests still skipped.
- Thirteen frontend auth tests passed (including refresh/sign-out races); TypeScript with stricter checks and the production build passed.
- Python deployment/verification scripts compile and their CLI help commands work.
- Local Vite landing page rendered in Chrome. Complete browser workflow still requires the backend/DynamoDB dependency.
- Required-integration mode correctly fails when DynamoDB cannot be reached.
- Terraform formatting/provider validation, real cloud resource inventory, image builds and pushes, infrastructure apply, live Cognito sign-in, cloud smoke and scaling/cache evidence remain unverified.

## Documentation used

- [AWS provider S3 Vectors index](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3vectors_index)
- [CloudFront VPC origin prerequisites](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html)
- [ECS target tracking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html)
- [Cognito InitiateAuth (password and refresh-token sign-in)](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_InitiateAuth.html)
- [Cognito AdminCreateUser](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminCreateUser.html)
