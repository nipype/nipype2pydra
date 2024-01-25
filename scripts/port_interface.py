import sys
import yaml
from pathlib import Path
import nipype2pydra.task
import nipype2pydra.utils

outputs_path = Path(__file__).parent.parent / "outputs" / "testing"

outputs_path.mkdir(parents=True, exist_ok=True)

spec_file = sys.argv[1]
with open(spec_file) as f:
    spec = yaml.load(f, Loader=yaml.SafeLoader)

converter = nipype2pydra.task.TaskConverter.load(
    output_module=spec["nipype_module"].split("interfaces.")[-1]
    + ".auto."
    + nipype2pydra.utils.to_snake_case(spec["task_name"]),
    **spec,
)
converter.generate(outputs_path)
