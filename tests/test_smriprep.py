from pathlib import Path
import yaml
from nipype2pydra.cli import workflow
from nipype2pydra.utils import show_cli_trace
from nipype2pydra.workflow import WorkflowConverter


def test_smriprep_conversion(pkg_dir, cli_runner):

    output_dir = Path(pkg_dir) / "outputs"

    if not output_dir.exists():
        output_dir.mkdir()

    result = cli_runner(
        workflow,
        [
            f"{pkg_dir}/example-specs/smriprep.yaml",
            f"{pkg_dir}/outputs/smriprep_new.py"
        ]
    )

    assert result.exit_code == 0, show_cli_trace(result)


def test_smriprep_graph(pkg_dir, cli_runner):

    output_dir = Path(pkg_dir) / "outputs"

    if not output_dir.exists():
        output_dir.mkdir()

    with open(f"{pkg_dir}/example-specs/smriprep.yaml") as f:
        spec = yaml.safe_load(f)

    converter = WorkflowConverter(spec)

    converter.save_graph(output_dir / "smriprep-graph.svg")