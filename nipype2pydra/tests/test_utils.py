from nipype2pydra.utils import extract_args, get_source_code
from nipype2pydra.testing import test_line_number_of_function


def test_split_parens_contents1():
    assert extract_args(
        "def foo(a, b, c):\n    return a",
    ) == ("def foo(", ["a", "b", "c"], "):\n    return a")


def test_split_parens_contents2():
    assert extract_args(
        "foo(a, 'b, c')",
    ) == ("foo(", ["a", "'b, c'"], ")")


def test_split_parens_contents2a():
    assert extract_args(
        'foo(a, "b, c")',
    ) == ("foo(", ["a", '"b, c"'], ")")


def test_split_parens_contents2b():
    assert extract_args("foo(a, 'b, \"c')") == ("foo(", ["a", "'b, \"c'"], ")")


def test_split_parens_contents3():
    assert extract_args(
        "foo(a, bar(b, c))",
    ) == ("foo(", ["a", "bar(b, c)"], ")")


def test_split_parens_contents3a():
    assert extract_args(
        "foo(a, bar[b, c])",
    ) == ("foo(", ["a", "bar[b, c]"], ")")


def test_split_parens_contents3b():
    assert extract_args(
        "foo(a, bar([b, c]))",
    ) == ("foo(", ["a", "bar([b, c])"], ")")


def test_split_parens_contents5():
    assert extract_args(
        "foo(a, '\"b\"', c)",
    ) == ("foo(", ["a", "'\"b\"'", "c"], ")")


def test_split_parens_contents6():
    assert extract_args(
        r"foo(a, '\'b\'', c)",
    ) == ("foo(", ["a", r"'\'b\''", "c"], ")")


def test_split_parens_contents6a():
    assert extract_args(
        r"foo(a, '\'b\', c')",
    ) == ("foo(", ["a", r"'\'b\', c'"], ")")


def test_split_parens_contents7():
    assert extract_args(
        '"""Module explanation"""\ndef foo(a, b, c)',
    ) == ('"""Module explanation"""\ndef foo(', ["a", "b", "c"], ")")


def test_split_parens_contents8():
    assert extract_args(
        """related_filetype_sets = [(".hdr", ".img", ".mat"), (".nii", ".mat"), (".BRIK", ".HEAD")]""",
    ) == (
        "related_filetype_sets = [",
        ['(".hdr", ".img", ".mat")', '(".nii", ".mat")', '(".BRIK", ".HEAD")'],
        "]",
    )


def test_split_parens_contents9():
    assert extract_args('foo(cwd=bar("tmpdir"), basename="maskexf")') == (
        "foo(",
        ['cwd=bar("tmpdir")', 'basename="maskexf"'],
        ")",
    )


def test_source_code():
    assert get_source_code(test_line_number_of_function).splitlines()[:2] == [
        "# Original source at L1 of <nipype2pydra-install>/testing.py",
        "def test_line_number_of_function():",
    ]
