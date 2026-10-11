"""Register paper functions and their command-line argument schemas."""

from dataclasses import dataclass
from functools import cached_property
import inspect
from typing import Callable

from pydantic import create_model


@dataclass
class Tool:
    function: Callable

    @cached_property
    def arguments(self):
        return create_model(
            self.function.__name__ + "Arguments",
            **{name: (parameter.annotation, parameter.default
                      if parameter.default is not inspect.Parameter.empty else ...)
               for name, parameter in inspect.signature(self.function).parameters.items()},
        )

    def schema(self, *, include_output=True):
        schema = {
            "name": self.function.__name__,
            "description": self.function.__doc__ or "",
            "inputSchema": self.arguments.model_json_schema(),
        }
        if include_output:
            schema["outputSchema"] = create_model(
                self.function.__name__ + "Output",
                result=(inspect.signature(self.function).return_annotation, ...),
            ).model_json_schema()
        return schema


TOOLS: dict[str, Tool] = {}


def tool(function):
    TOOLS[function.__name__] = Tool(function)
    return function
