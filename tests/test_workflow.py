from pathlib import Path
import yaml
import pytest
from nipype2pydra.cli import workflow
from nipype2pydra.utils import show_cli_trace
from nipype2pydra.workflow import WorkflowConverter


# @pytest.mark.xfail(reason="Workflow conversion hasn't been fully implemented yet")
def test_workflow_conversion(workflow_spec_file: Path, cli_runner, outputs_dir: Path):

    output_file = outputs_dir / f"{workflow_spec_file.stem}.py"

    result = cli_runner(
        workflow,
        [
            str(workflow_spec_file),
            str(output_file)
        ]
    )

    assert result.exit_code == 0, show_cli_trace(result)


# @pytest.mark.xfail(reason="Workflow conversion hasn't been fully implemented yet")
def test_workflow_graph(workflow_spec_file, outputs_dir):

    with open(workflow_spec_file) as f:
        spec = yaml.safe_load(f)

    converter = WorkflowConverter(spec)

    converter.save_graph(outputs_dir / f"{workflow_spec_file.stem}.svg")
