# AWS deployment

This directory defines RAGcat's AWS deployment in `ap-southeast-2`: CloudFront in front of an ALB with two ECS Fargate services (`api`, `qa`), two SQS-triggered Lambda workers (`ingest`, `embed`), DynamoDB, S3 Vectors, Valkey and Bedrock.

## Prerequisites and existing resources

- Terraform 1.12+, AWS provider 6.25+ (below 7), Docker with buildx, Node 22.16+, and the backend Python environment.
- An AWS CLI profile for the target account in `ap-southeast-2` (`AWS_PROFILE`; the Makefile default is `diana`).
- An existing Cognito User Pool ID. The pool is not managed by this stack; Terraform only adds RAGcat's own app client (password and refresh-token sign-in, no hosted login page, no callback URLs).
- Two private S3 buckets created by hand (public access blocked, AES256), passed as `files_bucket` and `web_bucket`:
  - **files:** enable EventBridge notifications in the console.
  - **web:** paste the CloudFront OAC bucket policy once the distribution exists.
- Model invocation permission for `amazon.titan-embed-text-v2:0` and `google.gemma-3-12b-it`. Seeing models in the catalog does not prove permission to invoke them.
- Cloud runtimes explicitly select the Bedrock QA, embedding and vision adapters. Local `make backend` instead uses Claude QA/context and OpenAI `text-embedding-3-small` (see the root `.env.local.example`); no local API keys are deployed. Keep query/index embedding models identical, and re-embed documents after a model change.
- Optional: an existing ECS cluster ARN and an existing VPC/subnet set. A reused network needs an attached internet gateway, private-subnet outbound access, and subnets in two AZs. A reused ECS cluster needs Container Insights enabled for task-count dashboard metrics; otherwise inspect task counts through ECS scaling activities.

`name_prefix` (default `ragcat`) prefixes every resource name, and `tags` adds any owner or cost-allocation tags your account requires.

First run:

```sh
docker compose up -d dynamodb
make test-integration
make test
make build
aws sso login --profile "$AWS_PROFILE"
make cloud-audit
```

`cloud-audit` only reads account metadata and writes `infra/inventory.json`. It does not create resources or print credentials. AccessDenied checks are reported separately; a successful catalog/list call does not certify all create/update permissions. Review the existing resources before deciding whether to reuse the network and cluster.

### Restricted shared account

Some accounts (for example an organization's shared sandbox) don't allow creating VPCs, internet gateways, security groups or IAM roles, or adding security-group rules. Set both `existing_network` and `shared_account` (examples in `terraform.tfvars.example`):

- **Network:** an existing VPC whose private subnets route out through a NAT gateway, so the stack creates no VPC or NAT.
- **Security groups:** the account's own.
  - The ALB uses a group that allows 443 in.
  - Runtimes and Valkey use a group whose members can reach each other, so the ALB reaches tasks on 8080 and tasks reach Valkey on 6379.
- **IAM:** the account's existing ECS execution, ECS task and Lambda roles replace the per-runtime roles in `iam.tf`. Their grants belong to the account; if a call is denied at runtime, ask the account administrator to allow it.
- **ALB:** a private CloudFront VPC origin needs a security-group rule from CloudFront's managed group, which can't be added. Instead:
  - The ALB is internet-facing with HTTPS on `origin_domain` (an ACM certificate validated in the domain's Route 53 zone).
  - CloudFront connects with HTTPS and sends a random secret header (`X-RAGcat-Origin`). The ALB forwards only requests that carry it; direct requests get the 404 default.
  - So the API still has one entry point, and the widget rate limit can still trust `CloudFront-Viewer-Address`.
- **Site name:** CloudFront serves the site on `site_domain` with a us-east-1 ACM certificate. Apply waits until it is ISSUED: in the us-east-1 ACM console, choose "Create records in Route 53" for its validation CNAME. After the apply, add an A alias record for the name to the distribution (no AAAA yet, so IPv6-only clients can't reach it). The `*.cloudfront.net` name keeps working.

Terraform can't refresh an SSO profile's token itself (`failed to refresh cached credentials`). `make infra-plan` and `make infra-apply` therefore pass it the CLI's short-lived credentials (`aws configure export-credentials`).

Copy `terraform.tfvars.example` to `terraform.tfvars` and replace its placeholders with verified values. The state and tfvars are ignored by Git. Keep the Terraform state: losing it would prevent safe updates to already-created resources. Before multi-user use, configure a remote state backend with locking.

## Bootstrap and workload deployment

The image repositories must exist before the container images can be pushed. `deploy_workloads = false` creates the infrastructure and authentication client without ECS tasks or Lambda functions. This bootstrap **already provisions** the ALB, cache (and, with a new VPC, a NAT gateway) and other resources with ongoing costs.

```sh
make infra-init
terraform -chdir=infra fmt
make infra-validate
make infra-plan
make infra-apply
make cloud-images IMAGE_TAG=release-20261014-1
```

Review the saved plan before `infra-apply`. Do not import or rename shared resources into this stack: reuse the User Pool and optional cluster/network through variables. With a new VPC, if IAM denies creation of the CloudFront VPC-origin service-linked role, have that permission granted rather than opening the ALB.

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
| Management | `/v1/*` → CloudFront VPC origin → internal ALB → `api` ECS service (in a restricted shared account: HTTPS to the public ALB with the secret origin header). |
| Questions | ALB rule `/v1/assistants/*/ask` and `/v1/widget/*/ask` (Website widget) takes priority and targets the separate `qa` service. API caching and response compression are disabled for SSE. The api reads the built `widget.html` from `RAGCAT_WIDGET_TEMPLATE_URL` (the CloudFront domain) to serve `/v1/widget/{aid}/frame`. |
| Upload | Browser posts directly to the private files S3 bucket using a presigned POST; bucket CORS permits the site origin. |
| Parse | Files bucket EventBridge events for `uploads/` → parse SQS → ingest Lambda. Generated `pages/` objects cannot retrigger ingestion. |
| Publish/delete | API sends embed SQS messages → embed Lambda reconciles S3 Vectors and document state. |
| Page preview | Backend returns an expiring S3 presigned GET URL after checking ownership. No public CloudFront `/pages/*` route exposes the private thumbnails. |
| Application data | One on-demand DynamoDB table with PK/SK and GSI1. |
| Retrieval | S3 Vectors cosine index matches Titan's configured dimensions. Assistant/Document IDs and `embedding_key` are filterable; large text and citation fields are non-filterable metadata. Queries never mix different embedding spaces. |
| Cache | TLS Valkey shared by API, QA, and workers preserves cross-process config invalidation, cached query vectors and versioned answer keys. |

All runtimes run in private subnets. For a new VPC there is one NAT gateway, used for AWS APIs, image pulls and Cognito JWKS. This reduces gateway count but makes outbound access depend on one AZ. Valkey uses one small primary and no replica: a cache failure falls back to cache misses, although requests may slow down. Both are cost/availability tradeoffs to revisit as traffic grows.

API tasks scale from 1–2 and QA tasks from 1–4 using `ALBRequestCountPerTarget`; initial targets are 300 and 60 requests per task per minute, respectively. Tune them from observed service capacity. Desired task count is excluded from Terraform drift correction so applying a deployment does not undo auto-scaling.

Lambda SQS mappings cap concurrency at 5 ingest and 2 embed, with batch size 1. Function timeout is 900 seconds and queue visibility is 5400 seconds. DLQs retain failures after three receives. Reserved Lambda concurrency is not allocated.

## Smoke and load tests

Set `RAGCAT_ACCESS_TOKEN` in your terminal to a current Cognito **access** token without committing or displaying it. Scripts take the credential from the environment and never print it. For local-only testing, `smoke_cloud.py` also accepts `dev:<name>` when the origin is localhost.

```sh
cd backend
uv run python ../scripts/smoke_cloud.py --base-url https://YOUR_DISTRIBUTION.cloudfront.net --keep
```

The smoke test creates a marked Assistant and Document, waits for parsing, loads a signed page image, edits a Passage with `If-Match`, embeds, publishes, and checks two SSE answers: a cold result with citations followed by a cache hit. S3 requests use a separate client without the owner's Authorization header. `--keep` retains the demonstration Document; without it, only the test's newly uploaded Document is deleted. The empty test Assistant remains because the current API does not support deleting Assistants. Reuse its printed ID with `--assistant-id` on subsequent runs.

To exercise auto-scaling:

```sh
# API traffic: no per-request model invocations.
uv run python ../scripts/load_cloud.py --base-url https://YOUR_DISTRIBUTION.cloudfront.net --seconds 300 --requests-per-second 10

# QA traffic: use the smoke-test Assistant. Warmup proves that answers are cached first.
uv run python ../scripts/load_cloud.py --base-url https://YOUR_DISTRIBUTION.cloudfront.net --assistant-id ast_YOUR_SMOKE_ASSISTANT --seconds 300 --requests-per-second 5
```

The load tool bounds concurrency, duration and rate. QA load stops if a response stops hitting the cache, to prevent unexpected repeated model calls. It also stops on expired/forbidden credentials. A completed request loop does **not** establish that scaling occurred: check ECS scaling activities and task counts, ALB per-target requests and latency/error rates, then wait for scale-in after traffic stops.

The CloudWatch dashboard includes ECS CPU/task counts, ALB requests per target, cache hits/misses, answer latency and queue backlog. QA completion logs are JSON with no question, answer text, or authentication token. Alarms flag DLQs, Lambda errors and unhealthy targets.

## Documentation used

- [AWS provider S3 Vectors index](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3vectors_index)
- [CloudFront VPC origin prerequisites](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html)
- [ECS target tracking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html)
- [Cognito InitiateAuth (password and refresh-token sign-in)](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_InitiateAuth.html)
- [Cognito AdminCreateUser](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminCreateUser.html)
