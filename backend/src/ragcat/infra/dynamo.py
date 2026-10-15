"""Single DynamoDB table shared by all contexts (domain-design.md §7)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from ragcat.shared.config import Settings

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


def serialize(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _serializer.serialize(v) for k, v in item.items() if v is not None}


def deserialize(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _deserializer.deserialize(v) for k, v in item.items()}


def plain(value: Any) -> Any:
    """Turn DynamoDB Decimals back into ints/floats for values that are not positions."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def is_conditional_failure(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    return code in ("ConditionalCheckFailedException", "TransactionCanceledException")


class Table:
    def __init__(self, settings: Settings) -> None:
        kwargs: dict[str, Any] = {"region_name": settings.region}
        if settings.dynamodb_endpoint:
            kwargs.update(
                endpoint_url=settings.dynamodb_endpoint,
                aws_access_key_id="local",
                aws_secret_access_key="local",
            )
        self.name = settings.table_name
        self.client = boto3.client("dynamodb", **kwargs)

    # Low-level helpers keep one serialization path for single writes and transactions.

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        out = self.client.get_item(TableName=self.name, Key=serialize({"PK": pk, "SK": sk}), ConsistentRead=True)
        return deserialize(out["Item"]) if "Item" in out else None

    def put(self, item: dict[str, Any], condition: str | None = None) -> bool:
        kwargs: dict[str, Any] = {"TableName": self.name, "Item": serialize(item)}
        if condition:
            kwargs["ConditionExpression"] = condition
        try:
            self.client.put_item(**kwargs)
            return True
        except ClientError as exc:
            if is_conditional_failure(exc):
                return False
            raise

    def update(
        self,
        pk: str,
        sk: str,
        *,
        set_fields: dict[str, Any] | None = None,
        add_fields: dict[str, Any] | None = None,
        delete_from_sets: dict[str, set[str]] | None = None,
        condition: str | None = None,
        condition_values: dict[str, Any] | None = None,
        return_new: bool = False,
    ) -> dict[str, Any] | None | bool:
        """SET/REMOVE (None values remove), ADD and DELETE in one call.

        Returns False when the condition fails, the new item when `return_new`, else True.
        """
        names: dict[str, str] = {}
        values: dict[str, Any] = dict(condition_values or {})
        sets, removes, adds, deletes = [], [], [], []
        for i, (field, value) in enumerate((set_fields or {}).items()):
            names[f"#s{i}"] = field
            if value is None:
                removes.append(f"#s{i}")
            else:
                values[f":s{i}"] = value
                sets.append(f"#s{i} = :s{i}")
        for i, (field, value) in enumerate((add_fields or {}).items()):
            names[f"#a{i}"] = field
            values[f":a{i}"] = value
            adds.append(f"#a{i} :a{i}")
        for i, (field, value) in enumerate((delete_from_sets or {}).items()):
            names[f"#d{i}"] = field
            values[f":d{i}"] = value
            deletes.append(f"#d{i} :d{i}")
        parts = []
        if sets:
            parts.append("SET " + ", ".join(sets))
        if removes:
            parts.append("REMOVE " + ", ".join(removes))
        if adds:
            parts.append("ADD " + ", ".join(adds))
        if deletes:
            parts.append("DELETE " + ", ".join(deletes))
        kwargs: dict[str, Any] = {
            "TableName": self.name,
            "Key": serialize({"PK": pk, "SK": sk}),
            "UpdateExpression": " ".join(parts),
        }
        if condition:
            kwargs["ConditionExpression"] = condition
            names.update(_condition_names(condition))
        if names:
            kwargs["ExpressionAttributeNames"] = names
        if values:
            kwargs["ExpressionAttributeValues"] = serialize(values)
        if return_new:
            kwargs["ReturnValues"] = "ALL_NEW"
        try:
            out = self.client.update_item(**kwargs)
        except ClientError as exc:
            if is_conditional_failure(exc):
                return False
            raise
        return deserialize(out["Attributes"]) if return_new else True

    def delete(self, pk: str, sk: str, condition: str | None = None, condition_values: dict[str, Any] | None = None) -> bool:
        kwargs: dict[str, Any] = {"TableName": self.name, "Key": serialize({"PK": pk, "SK": sk})}
        if condition:
            kwargs["ConditionExpression"] = condition
            names = _condition_names(condition)
            if names:
                kwargs["ExpressionAttributeNames"] = names
            if condition_values:
                kwargs["ExpressionAttributeValues"] = serialize(condition_values)
        try:
            self.client.delete_item(**kwargs)
            return True
        except ClientError as exc:
            if is_conditional_failure(exc):
                return False
            raise

    def query_prefix(self, pk: str, sk_prefix: str, *, index: str | None = None) -> list[dict[str, Any]]:
        pk_name, sk_name = ("GSI1PK", "GSI1SK") if index else ("PK", "SK")
        kwargs: dict[str, Any] = {
            "TableName": self.name,
            "KeyConditionExpression": "#pk = :pk AND begins_with(#sk, :sk)",
            "ExpressionAttributeNames": {"#pk": pk_name, "#sk": sk_name},
            "ExpressionAttributeValues": serialize({":pk": pk, ":sk": sk_prefix}),
        }
        if index:
            kwargs["IndexName"] = index
        else:
            kwargs["ConsistentRead"] = True
        items: list[dict[str, Any]] = []
        while True:
            out = self.client.query(**kwargs)
            items.extend(deserialize(i) for i in out.get("Items", []))
            if "LastEvaluatedKey" not in out:
                return items
            kwargs["ExclusiveStartKey"] = out["LastEvaluatedKey"]

    def batch_put(self, items: list[dict[str, Any]]) -> None:
        self._batch([{"PutRequest": {"Item": serialize(i)}} for i in items])

    def batch_delete(self, keys: list[tuple[str, str]]) -> None:
        self._batch([{"DeleteRequest": {"Key": serialize({"PK": pk, "SK": sk})}} for pk, sk in keys])

    def _batch(self, requests: list[dict[str, Any]]) -> None:
        for start in range(0, len(requests), 25):
            pending = {self.name: requests[start : start + 25]}
            while pending:
                out = self.client.batch_write_item(RequestItems=pending)
                pending = out.get("UnprocessedItems") or {}

    def transact(self, operations: list[dict[str, Any]]) -> bool:
        """Operations use the low-level shape but with plain Python values (serialized here)."""
        items = []
        for op in operations:
            (kind, body), = op.items()
            body = dict(body, TableName=self.name)
            for field in ("Item", "Key", "ExpressionAttributeValues"):
                if field in body:
                    body[field] = serialize(body[field])
            items.append({kind: body})
        try:
            self.client.transact_write_items(TransactItems=items)
            return True
        except ClientError as exc:
            if is_conditional_failure(exc):
                return False
            raise

    def ensure_exists(self) -> None:
        """Create the table if missing (local development and tests only; AWS uses Terraform)."""
        try:
            self.client.describe_table(TableName=self.name)
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
        self.client.create_table(
            TableName=self.name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK", "GSI1PK", "GSI1SK")],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        self.client.get_waiter("table_exists").wait(TableName=self.name)

    def drop(self) -> None:
        self.client.delete_table(TableName=self.name)


def _condition_names(expression: str) -> dict[str, str]:
    """Conditions reference attributes as #name; map each to itself."""
    import re

    return {f"#{n}": n for n in re.findall(r"#([A-Za-z_][A-Za-z0-9_]*)", expression)}
