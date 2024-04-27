import typing as ty
import attrs


@attrs.define
class ReturnStatement:

    vars: ty.List[str] = attrs.field(converter=lambda s: s.split(", "))
    indent: str = attrs.field()

    def __str__(self):
        return f"{self.indent}return {', '.join(self.vars)}"


@attrs.define
class CommentStatement:

    comment: str = attrs.field()
    indent: str = attrs.field()

    def __str__(self):
        return f"{self.indent}# {self.comment}"


@attrs.define
class DocStringStatement:

    docstring: str = attrs.field()
    indent: str = attrs.field()

    def __str__(self):
        return f"{self.indent}{self.docstring}"
