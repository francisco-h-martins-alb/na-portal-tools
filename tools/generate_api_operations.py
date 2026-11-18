"""Generate API Explorer metadata from a local NA-PORTAL OpenAPI JSON file."""

import argparse
import json
import re
from pathlib import Path


METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
MISSING = object()


def documented_example(node):
    if "example" in node:
        return node["example"]
    return next(
        (example["value"] for example in node.get("examples", {}).values() if "value" in example),
        MISSING,
    )


def schema_example(spec, schema, refs=()):
    example = documented_example(schema)
    if example is not MISSING:
        return example
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#components/"):
            ref = "#/" + ref[1:]
        if not ref.startswith("#/"):
            raise ValueError(f"Expected a local schema reference, got {ref!r}")
        if ref in refs:
            return {}
        target = spec
        for key in ref.removeprefix("#/").split("/"):
            target = target[key.replace("~1", "/").replace("~0", "~")]
        return schema_example(spec, target, (*refs, ref))
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]
    if "allOf" in schema or "properties" in schema or schema.get("type") == "object":
        result = {}
        for part in schema.get("allOf", []):
            result.update(schema_example(spec, part, refs))
        for name, prop in schema.get("properties", {}).items():
            if not prop.get("readOnly"):
                result[name] = schema_example(spec, prop, refs)
        return result
    if schema.get("type") == "array":
        return [schema_example(spec, schema["items"], refs)]
    return {"integer": 0, "number": 0, "boolean": False,
            "date": "2000-01-01", "string": "string"}.get(schema.get("type"), {})


def safe_example(value):
    if isinstance(value, dict):
        return {
            key: "REPLACE_ME" if re.search(r"password|secret|token|api.?key", key, re.I)
            else safe_example(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [safe_example(item) for item in value]
    return value


def generate(spec):
    operations = []
    for path, item in spec["paths"].items():
        placeholders = re.findall(r"\{([^{}]+)\}", path)
        for method, operation in item.items():
            if method not in METHODS:
                continue
            entry = {
                "tag": operation["tags"][0], "method": method.upper(),
                "path": path, "summary": operation["summary"], "parameters": [],
            }
            parameters = {
                (parameter["in"], parameter["name"]): parameter
                for parameter in [*item.get("parameters", []), *operation.get("parameters", [])]
            }
            for location, name in parameters:
                parameter = parameters[location, name]
                if location == "path" and name not in placeholders:
                    # The upstream /netwin/nacatalogs/{id} operations label this parameter idCatEntity.
                    unmatched = set(placeholders) - {key for loc, key in parameters if loc == "path"}
                    if len(unmatched) != 1:
                        raise ValueError(f"Unmatched path parameter {name!r} in {method} {path}")
                    name = unmatched.pop()
                schema = parameter.get("schema", {})
                metadata = {"name": name, "in": location, "type": schema.get("type", "string"),
                            "required": location == "path" or parameter.get("required", False)}
                example = documented_example(parameter)
                if example is MISSING:
                    example = documented_example(schema)
                if example is not MISSING:
                    metadata["example"] = safe_example(example)
                entry["parameters"].append(metadata)
            body = operation.get("requestBody", {})
            media = body.get("content", {}).get("application/json")
            if media is not None:
                schema = media["schema"]
                example = documented_example(media)
                if example is MISSING:
                    example = documented_example(schema)
                entry["body"] = {
                    "required": body.get("required", False),
                    "schemaDerived": example is MISSING,
                    "example": safe_example(schema_example(spec, schema) if example is MISSING else example),
                }
            if method == "get" and any(
                status.startswith("2") and not response.get("content")
                for status, response in operation["responses"].items()
            ):
                entry["allowEmptyResponse"] = True
            operations.append(entry)
    tags = {tag["name"]: index for index, tag in enumerate(spec.get("tags", []))}
    return sorted(operations, key=lambda operation: tags.get(operation["tag"], len(tags)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    operations = generate(json.loads(args.spec.read_text(encoding="utf-8")))
    destination = Path(__file__).resolve().parents[1] / "web" / "api_operations.json"
    records = ",\n".join("  " + json.dumps(operation, ensure_ascii=False) for operation in operations)
    destination.write_text("[\n" + records + "\n]\n", encoding="utf-8")
