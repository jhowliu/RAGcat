"""Read-only account inventory. Run with backend/.venv/bin/python; never print credentials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

CONFIG = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 0})


def inventory(profile: str, prefix: str) -> dict:
    session = boto3.Session(profile_name=profile, region_name="ap-southeast-2")
    identity = session.client("sts", config=CONFIG).get_caller_identity()
    result = {"region": "ap-southeast-2", "prefix": prefix, "account_id": identity["Account"], "checks": {}}

    def check(name, fn):
        try:
            result["checks"][name] = {"status": "ok", "items": fn()}
        except (BotoCoreError, ClientError) as error:
            result["checks"][name] = {"status": "unavailable", "error": str(error)}

    def client(service):
        return session.client(service, config=CONFIG)

    def pages(service, operation, key, **kwargs):
        api = client(service)
        return [item for page in api.get_paginator(operation).paginate(**kwargs) for item in page.get(key, [])]

    def pools():
        api = client("cognito-idp")
        candidates = api.list_user_pools(MaxResults=60).get("UserPools", [])
        items = []
        for pool in candidates:
            # Names/IDs are enough to select a shared pool; do not fetch user records or client secrets.
            item = {"id": pool["Id"], "name": pool["Name"]}
            if len(candidates) == 1 or prefix in pool["Name"]:
                detail = api.describe_user_pool(UserPoolId=pool["Id"])["UserPool"]
                domain = detail.get("CustomDomain") or detail.get("Domain")
                if domain:
                    item["hosted_ui"] = "https://" + (domain if "." in domain else f"{domain}.auth.ap-southeast-2.amazoncognito.com")
                    item["managed_login_version"] = api.describe_user_pool_domain(Domain=domain).get("DomainDescription", {}).get("ManagedLoginVersion", 1)
                item["identity_providers"] = [p["ProviderName"] for p in api.list_identity_providers(UserPoolId=pool["Id"], MaxResults=60).get("Providers", [])]
            items.append(item)
        return items

    def clusters():
        arns = pages("ecs", "list_clusters", "clusterArns")
        if not arns:
            return []
        result = []
        for start in range(0, len(arns), 100):
            result.extend({"arn": c["clusterArn"], "name": c["clusterName"], "status": c["status"], "settings": c.get("settings", [])} for c in client("ecs").describe_clusters(clusters=arns[start:start + 100], include=["SETTINGS"]).get("clusters", []))
        return result

    check("cognito_user_pools", pools)
    check("ecs_clusters", clusters)
    check("dynamodb_tables", lambda: [name for name in pages("dynamodb", "list_tables", "TableNames") if name.startswith(prefix)])
    check("s3_buckets", lambda: [b["Name"] for b in client("s3").list_buckets().get("Buckets", []) if b["Name"].startswith(prefix)])
    check("ecr_repositories", lambda: [{"name": r["repositoryName"], "uri": r["repositoryUri"]} for r in pages("ecr", "describe_repositories", "repositories") if r["repositoryName"].startswith(prefix)])
    check("sqs_queues", lambda: client("sqs").list_queues(QueueNamePrefix=prefix).get("QueueUrls", []))
    check("lambda_functions", lambda: [{"name": f["FunctionName"], "arn": f["FunctionArn"]} for f in pages("lambda", "list_functions", "Functions") if f["FunctionName"].startswith(prefix)])
    check("vpcs", lambda: [{"id": v["VpcId"], "cidr": v["CidrBlock"], "default": v["IsDefault"], "name": next((t["Value"] for t in v.get("Tags", []) if t["Key"] == "Name"), "")} for v in client("ec2").describe_vpcs().get("Vpcs", [])])
    check("prefixed_subnets", lambda: [{"id": s["SubnetId"], "vpc_id": s["VpcId"], "az": s["AvailabilityZone"]} for s in client("ec2").describe_subnets(Filters=[{"Name": "tag:Name", "Values": [f"{prefix}*"]}]).get("Subnets", [])])
    check("s3_vector_buckets", lambda: [b for b in client("s3vectors").list_vector_buckets().get("vectorBuckets", []) if b["vectorBucketName"].startswith(prefix)])
    check("bedrock_model_catalog", lambda: [{"id": m["modelId"], "inputs": m.get("inputModalities", []), "outputs": m.get("outputModalities", [])} for m in client("bedrock").list_foundation_models().get("modelSummaries", []) if m["modelId"] in ("amazon.titan-embed-text-v2:0", "google.gemma-3-12b-it")])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="diana")
    parser.add_argument("--prefix", default="ragcat", help="name prefix of the resources to list")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = inventory(args.profile, args.prefix)
    except (BotoCoreError, ClientError) as error:
        print(json.dumps({"status": "blocked", "stage": "AWS identity/SSO", "error": str(error)}, indent=2))
        return 2
    payload = json.dumps(report, indent=2, default=str) + "\n"
    if args.output:
        args.output.write_text(payload)
    print(payload, end="")
    return 0 if all(c["status"] == "ok" for c in report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
