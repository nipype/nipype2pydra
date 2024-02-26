import sys
import yaml
from pathlib import Path
import nipype2pydra.workflow
import nipype2pydra.utils

outputs_path = Path(__file__).parent.parent / "outputs" / "testing"

outputs_path.mkdir(parents=True, exist_ok=True)

spec_file = sys.argv[1]
with open(spec_file) as f:
    spec = yaml.load(f, Loader=yaml.SafeLoader)

converter = nipype2pydra.workflow.WorkflowConverter(spec)
converter.generate(outputs_path)
