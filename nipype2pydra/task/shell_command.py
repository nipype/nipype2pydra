import re
import attrs
from .base import BaseTaskConverter


@attrs.define
class ShellCommandTaskConverter(BaseTaskConverter):
    def generate_task_str(self, filename, input_fields, nonstd_types, output_fields):
        """writing pydra task to the dile based on the input and output spec"""

        base_imports = [
            "from pydra.engine import specs",
        ]

        task_base = "ShellCommandTask"
        base_imports.append("from pydra.engine import ShellCommandTask")

        try:
            executable = self.nipype_interface._cmd
        except AttributeError:
            executable = None
        if not executable:
            executable = self.nipype_interface.cmd
            if not isinstance(executable, str):
                raise RuntimeError(
                    f"Could not find executable for {self.nipype_interface}"
                )

        def types_to_names(spec_fields):
            spec_fields_str = []
            for el in spec_fields:
                el = list(el)
                tp_str = str(el[1])
                if tp_str.startswith("<class "):
                    tp_str = el[1].__name__
                else:
                    # Alter modules in type string to match those that will be imported
                    tp_str = tp_str.replace("typing", "ty")
                    tp_str = re.sub(r"(\w+\.)+(?<!ty\.)(\w+)", r"\2", tp_str)
                el[1] = "#" + tp_str + "#"
                spec_fields_str.append(tuple(el))
            return spec_fields_str

        input_fields_str = types_to_names(spec_fields=input_fields)
        output_fields_str = types_to_names(spec_fields=output_fields)
        functions_str = self.function_callables()
        spec_str = functions_str
        spec_str += f"input_fields = {input_fields_str}\n"
        spec_str += f"{self.task_name}_input_spec = specs.SpecInfo(name='Input', fields=input_fields, bases=(specs.ShellSpec,))\n\n"
        spec_str += f"output_fields = {output_fields_str}\n"
        spec_str += f"{self.task_name}_output_spec = specs.SpecInfo(name='Output', fields=output_fields, bases=(specs.ShellOutSpec,))\n\n"
        spec_str += f"class {self.task_name}({task_base}):\n"
        spec_str += '    """\n'
        spec_str += self.create_doctests(
            input_fields=input_fields, nonstd_types=nonstd_types
        )
        spec_str += '    """\n'
        spec_str += f"    input_spec = {self.task_name}_input_spec\n"
        spec_str += f"    output_spec = {self.task_name}_output_spec\n"
        if task_base == "ShellCommandTask":
            spec_str += f"    executable='{executable}'\n"

        spec_str = re.sub(r"'#([^'#]+)#'", r"\1", spec_str)

        imports = self.construct_imports(
            nonstd_types,
            spec_str,
            include_task=False,
            base=base_imports,
        )
        spec_str = "\n".join(imports) + "\n\n" + spec_str

        return spec_str
