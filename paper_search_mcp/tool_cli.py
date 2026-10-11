"""Call every registered paper operation directly from the command line."""

from __future__ import annotations

import argparse
import json
from typing import Any


def _boolean(value: str) -> bool:
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise argparse.ArgumentTypeError("expected true or false")


def _argument_type(schema: dict[str, Any]) -> Any:
    """Convert shell strings; the shared argument model performs final validation."""
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": _boolean,
    }.get(schema.get("type"), json.loads)


def build_tool_parser(tools: list[Any]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-search tool",
        description="Call a paper operation directly. Required arguments "
        "are positional; optional arguments use --kebab-case flags.",
    )
    parser.add_argument(
        "--list", action="store_true", dest="_list_tools",
        help="List paper operations, argument and output schemas as JSON",
    )
    subparsers = parser.add_subparsers(dest="_tool_name")
    for tool in tools:
        description = tool["description"] or tool["name"]
        command = subparsers.add_parser(
            tool["name"],
            help=description.splitlines()[0],
            description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            allow_abbrev=False,
        )
        properties = tool["inputSchema"].get("properties", {})
        required = set(tool["inputSchema"].get("required", []))
        for name, schema in properties.items():
            help_text = schema.get("description", schema.get("title", name))
            if name in required:
                command.add_argument(
                    name, type=_argument_type(schema), help=help_text,
                    **({"choices": schema["enum"]} if "enum" in schema else {}),
                )
                continue
            option = f"--{name.replace('_', '-')}"
            if "default" in schema:
                help_text += f" (default: {schema['default']!r})"
            kwargs: dict[str, Any] = {
                "dest": name, "default": argparse.SUPPRESS, "help": help_text,
            }
            if schema.get("type") == "boolean":
                kwargs["action"] = argparse.BooleanOptionalAction
            else:
                kwargs["type"] = _argument_type(schema)
                if "enum" in schema:
                    kwargs["choices"] = schema["enum"]
            command.add_argument(option, **kwargs)
        command.set_defaults(_tool_parameter_names=tuple(properties))
    return parser


async def cmd_tool(args: argparse.Namespace) -> int:
    try:
        from .operations import TOOLS

        tools = [tool.schema(include_output=args.list_tools) for tool in TOOLS.values()]
        parser = build_tool_parser(tools)
        argv = list(args.tool_args)
        if args.tool_help:
            argv.insert(0, "--help")
        if args.list_tools:
            argv.insert(0, "--list")
        parsed = parser.parse_args(argv)
        if parsed._list_tools:
            if parsed._tool_name is not None:
                parser.error("--list cannot be combined with a tool invocation")
            print(json.dumps(
                {"tools": tools},
                indent=2,
            ))
            return 0
        if parsed._tool_name is None:
            parser.error("a tool name or --list is required")
        arguments = {
            name: getattr(parsed, name)
            for name in parsed._tool_parameter_names
            if hasattr(parsed, name)
        }
        registered = TOOLS[parsed._tool_name]
        result = await registered.function(**registered.arguments.model_validate(arguments).model_dump())
        print(result if isinstance(result, str) else json.dumps(result, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1
