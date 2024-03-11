from nipype2pydra.utils import split_parens_contents


def test_split_parens_contents1():
    assert split_parens_contents(
        "def foo(a, b, c):\n    return a",
    ) == ("def foo(", ["a", "b", "c"], "):\n    return a")


def test_split_parens_contents2():
    assert split_parens_contents(
        "foo(a, 'b, c')",
    ) == ("foo(", ["a", "'b, c'"], ")")


def test_split_parens_contents2a():
    assert split_parens_contents(
        'foo(a, "b, c")',
    ) == ("foo(", ["a", '"b, c"'], ")")


def test_split_parens_contents2b():
    assert split_parens_contents("foo(a, 'b, \"c')") == ("foo(", ["a", "'b, \"c'"], ")")


def test_split_parens_contents3():
    assert split_parens_contents(
        "foo(a, bar(b, c))",
    ) == ("foo(", ["a", "bar(b, c)"], ")")


def test_split_parens_contents3a():
    assert split_parens_contents(
        "foo(a, bar[b, c])",
    ) == ("foo(", ["a", "bar[b, c]"], ")")


def test_split_parens_contents3b():
    assert split_parens_contents(
        "foo(a, bar([b, c]))",
    ) == ("foo(", ["a", "bar([b, c])"], ")")


def test_split_parens_contents5():
    assert split_parens_contents(
        "foo(a, '\"b\"', c)",
    ) == ("foo(", ["a", "'\"b\"'", "c"], ")")


def test_split_parens_contents6():
    assert split_parens_contents(
        r"foo(a, '\'b\'', c)",
    ) == ("foo(", ["a", r"'\'b\''", "c"], ")")


def test_split_parens_contents6a():
    assert split_parens_contents(
        r"foo(a, '\'b\', c')",
    ) == ("foo(", ["a", r"'\'b\', c'"], ")")


def test_split_parens_contents7():
    assert split_parens_contents(
        '"""Module explanation"""\ndef foo(a, b, c)',
    ) == ('"""Module explanation"""\ndef foo(', ["a", "b", "c"], ")")


def test_split_parens_contents8():
    assert split_parens_contents(
        """related_filetype_sets = [(".hdr", ".img", ".mat"), (".nii", ".mat"), (".BRIK", ".HEAD")]""",
    ) == (
        "related_filetype_sets = [",
        ['(".hdr", ".img", ".mat")', '(".nii", ".mat")', '(".BRIK", ".HEAD")'],
        "]",
    )


def test_split_parens_contents9():
    assert split_parens_contents(
        'foo(cwd=bar("tmpdir"), basename="maskexf")'
    ) == (
        "foo(",
        ['cwd=bar("tmpdir")', 'basename="maskexf"'],
        ")",
    )
