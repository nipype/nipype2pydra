import pytest
from nipype2pydra.cli.pkg_gen import pkg_gen
from nipype2pydra.utils import show_cli_trace

from conftest import EXAMPLE_PKG_GEN_DIR


@pytest.fixture(
    params=[
        str(p.relative_to(EXAMPLE_PKG_GEN_DIR)).replace("/", "-")[:-5]
        for p in (EXAMPLE_PKG_GEN_DIR).glob("**/*.yaml")
    ]
)
def pkg_gen_spec_file(request):
    return EXAMPLE_PKG_GEN_DIR.joinpath(*request.param.split("-")).with_suffix(".yaml")


def test_pkg_gen(pkg_gen_spec_file, cli_runner, tmp_path, tasks_template_args):
    outputs_dir = tmp_path / "output-dir"
    outputs_dir.mkdir()

    result = cli_runner(
        pkg_gen,
        [
            str(pkg_gen_spec_file),
            str(outputs_dir),
        ]
        + tasks_template_args,
    )
    assert result.exit_code == 0, show_cli_trace(result)
