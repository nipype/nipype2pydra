import yaml
import pytest
from nipype2pydra.cli import workflow
from nipype2pydra.utils import show_cli_trace
from nipype2pydra.workflow import WorkflowConverter


@pytest.mark.xfail(reason="Workflow conversion hasn't been fully implemented yet")
def test_workflow_conversion(workflow_spec_file, cli_runner, work_dir):

    output_file = work_dir / "pydra_module.py"

    result = cli_runner(
        workflow,
        [
            str(workflow_spec_file),
            str(output_file)
        ]
    )

    assert result.exit_code == 0, show_cli_trace(result)


@pytest.mark.xfail(reason="Workflow conversion hasn't been fully implemented yet")
def test_workflow_graph(workflow_spec_file, work_dir):

    with open(workflow_spec_file) as f:
        spec = yaml.safe_load(f)

    converter = WorkflowConverter(spec)

    converter.save_graph(work_dir / "smriprep-graph.svg")
