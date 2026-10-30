"""Publish RAGcat images/static files or export applied resource identifiers for Gradescope."""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import subprocess
import time
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def outputs() -> dict:
    result = subprocess.run(["terraform", f"-chdir={ROOT / 'infra'}", "output", "-json"], check=True, text=True, capture_output=True)
    return {name: value["value"] for name, value in json.loads(result.stdout).items()}


def session_for(profile: str, state: dict):
    # boto3 can't refresh this SSO profile's token (same as Terraform, see TF_AWS in the Makefile), so use the
    # CLI's short-lived credentials. They are passed to the session only, never printed.
    exported = json.loads(subprocess.run(["aws", "configure", "export-credentials", "--profile", profile, "--format", "process"], check=True, text=True, capture_output=True).stdout)
    session = boto3.Session(
        aws_access_key_id=exported["AccessKeyId"],
        aws_secret_access_key=exported["SecretAccessKey"],
        aws_session_token=exported["SessionToken"],
        region_name=state["region"],
    )
    identity = session.client("sts", config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 0})).get_caller_identity()
    if identity["Account"] != state["account_id"] or state["region"] != "ap-southeast-2":
        raise ValueError("AWS profile and Terraform state must identify the same Sydney account")
    return session


def publish_images(session, state: dict, tag: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag) or tag in ("latest", "unpublished"):
        raise ValueError("Supply a unique immutable release tag, not latest or unpublished")
    run(["docker", "info"])
    authorization = session.client("ecr").get_authorization_token()["authorizationData"][0]
    user, password = base64.b64decode(authorization["authorizationToken"]).decode().split(":", 1)
    registry = state["ecr_repositories"]["service"].split("/", 1)[0]
    # The password is never placed in argv, printed, or written to a project file.
    subprocess.run(["docker", "login", "--username", user, "--password-stdin", registry], input=password, text=True, check=True)
    for target in ("service", "worker"):
        image = f"{state['ecr_repositories'][target]}:{tag}"
        run(["docker", "buildx", "build", "--platform", "linux/arm64", "--provenance=false", "--target", target, "--tag", image, "--push", "."], cwd=ROOT / "backend")
    print(f"Published both images. Set image_tag = {json.dumps(tag)} and deploy_workloads = true, then review a new Terraform plan.")


def publish_web(session, state: dict) -> None:
    run(["npm", "run", "build"], cwd=ROOT / "web")
    s3 = session.client("s3")
    directory = ROOT / "web" / "dist"
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        key = path.relative_to(directory).as_posix()
        # Only content-hashed assets are immutable. HTML and named mascot files can change.
        cache = "public, max-age=31536000, immutable" if key.startswith("assets/") else "no-cache"
        s3.put_object(Bucket=state["web_bucket"], Key=key, Body=path.read_bytes(), ContentType=mimetypes.guess_type(key)[0] or "application/octet-stream", CacheControl=cache)
    response = session.client("cloudfront").create_invalidation(
        DistributionId=state["cloudfront_distribution_id"],
        InvalidationBatch={"Paths": {"Quantity": 1, "Items": ["/*"]}, "CallerReference": f"ragcat-web-{time.time_ns()}"},
    )
    print(f"Published {state['site_url']}; CloudFront invalidation {response['Invalidation']['Id']} is propagating.")


def submission(state: dict, target: Path) -> None:
    if not state["service_names"]:
        raise ValueError("Apply the workload stage first; a bootstrap-only stack is not a complete submission")
    # JSON string literals are valid YAML scalar syntax, so no extra YAML dependency is required.
    lines = ["cloudInfrastructure:"]
    for resource in state["cloud_resources"]:
        lines.extend([f"  - type: {json.dumps(resource['type'])}", f"    arn: {json.dumps(resource['arn'])}", f"    description: {json.dumps(resource['description'])}"])
    lines.extend(["", "metaData:", f"  qutUsernameTag: {json.dumps(state['qut_username'])}", ""])
    target.write_text("\n".join(lines))
    print(f"Exported {len(state['cloud_resources'])} applied resource identifiers to {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["images", "web", "submission"])
    parser.add_argument("--profile", default="diana")
    parser.add_argument("--tag")
    parser.add_argument("--output", type=Path, default=ROOT / "infra" / "submission-a3-infra.yml")
    args = parser.parse_args()
    try:
        state = outputs()
        if args.action == "submission":
            submission(state, args.output)
        else:
            session = session_for(args.profile, state)
            if args.action == "images":
                if not args.tag:
                    raise ValueError("images requires --tag RELEASE_TAG")
                publish_images(session, state, args.tag)
            else:
                publish_web(session, state)
    except (BotoCoreError, ClientError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Deployment stopped: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
