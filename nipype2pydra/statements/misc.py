import typing as ty
import re
import attrs
from typing_extensions import Self


@attrs.define
class ReturnStatement:

    vars: ty.List[str] = attrs.field(converter=lambda s: s.split(", "))
    indent: str = attrs.field()

    match_re = re.compile(r"(\s*)return (.*)", flags=re.MULTILINE | re.DOTALL)

    def __str__(self):
        return f"{self.indent}return {', '.join(self.vars)}"

    @classmethod
    def matches(cls, stmt) -> bool:
        return bool(cls.match_re.match(stmt))

    @classmethod
    def parse(cls, statement: str) -> Self:
        match = cls.match_re.match(statement)
        return cls(vars=match.group(2), indent=match.group(1))


@attrs.define
class CommentStatement:

    comment: str = attrs.field()
    indent: str = attrs.field()

    match_re = re.compile(r"^(\s*)#\s*(.*)")

    def __str__(self):
        return f"{self.indent}# {self.comment}"

    @classmethod
    def matches(cls, stmt) -> bool:
        return bool(cls.match_re.match(stmt))

    @classmethod
    def parse(cls, statement: str) -> Self:
        match = cls.match_re.match(statement)
        return cls(comment=match.group(2), indent=match.group(1))


@attrs.define
class DocStringStatement:

    docstring: str = attrs.field()
    indent: str = attrs.field()

    match_re = re.compile(r"^(\s*)(?='|\")(.*)", flags=re.MULTILINE | re.DOTALL)

    def __str__(self):
        return f"{self.indent}{self.docstring}"

    @classmethod
    def matches(cls, stmt) -> bool:
        return bool(cls.match_re.match(stmt))

    @classmethod
    def parse(cls, statement: str) -> Self:
        match = cls.match_re.match(statement)
        return cls(docstring=match.group(2), indent=match.group(1))
