import re
import attrs
from .workflow_build import AddInterfaceStatement


@attrs.define
class AddFunctionInterfaceStatement(AddInterfaceStatement):

    converted_interface = "FunctionTask"

    @property
    def arg_name_vals(self):
        name_vals = []
        for name, val in super().arg_name_vals:
            if name == "function":
                name = "func"
            elif name == "input_names":
                name = "input_spec"
                val = f"SpecInfo(name='FunctionIn', bases=(BaseSpec,), fields={to_fields_spec(val)[1]})"
            elif name == "output_names":
                name = "output_spec"
                val = f"SpecInfo(name='FunctionOut', bases=(BaseSpec,), fields={to_fields_spec(val)[1]})"
            name_vals.append((name, val))
        return name_vals


@attrs.define
class AddIdentityInterfaceStatement(AddInterfaceStatement):

    converted_interface = "FunctionTask"

    @property
    def arg_name_vals(self):
        fields_str = next(v for n, v in super().arg_name_vals if n.strip() == "fields")
        field_names, fields_spec = to_fields_spec(fields_str)
        name_vals = [
            ("func", f"lambda {', '.join(field_names)}: ({', '.join(field_names)})"),
            (
                "input_spec",
                f"SpecInfo(name='IdentityIn', bases=(BaseSpec,), fields={fields_spec})",
            ),
            (
                "output_spec",
                f"SpecInfo(name='IdentityOut', bases=(BaseSpec,), fields={fields_spec})",
            ),
        ]
        return name_vals


UTILITY_CONVERTERS = {
    "Function": AddFunctionInterfaceStatement,
    "IdentityInterface": AddIdentityInterfaceStatement,
}


def to_fields_spec(fields_str):
    field_names = re.findall(r"(?<='|\")\w+(?='|\")", fields_str)
    return (
        field_names,
        "[" + ",".join(f"('{name}', ty.Any)" for name in field_names) + "]",
    )
