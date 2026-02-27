"""Tests for io.schemas helpers."""

from allocation_core.io.schemas import (
    fmt_bool,
    pipe_join,
    pipe_split,
    to_bool,
    to_float,
    to_float_or_none,
    to_int,
)


class TestPipeHelpers:
    def test_pipe_join_list(self):
        assert pipe_join(["a", "b", "c"]) == "a|b|c"

    def test_pipe_join_empty(self):
        assert pipe_join([]) == ""
        assert pipe_join(None) == ""

    def test_pipe_join_skips_empty(self):
        assert pipe_join(["a", "", "c"]) == "a|c"

    def test_pipe_split_basic(self):
        assert pipe_split("a|b|c") == ["a", "b", "c"]

    def test_pipe_split_empty(self):
        assert pipe_split("") == []
        assert pipe_split(None) == []

    def test_pipe_split_single(self):
        assert pipe_split("only") == ["only"]

    def test_roundtrip(self):
        original = ["theke", "bar", "service"]
        assert pipe_split(pipe_join(original)) == original


class TestTypeCoercion:
    def test_to_float_valid(self):
        assert to_float("12.50") == 12.50

    def test_to_float_empty(self):
        assert to_float("") == 0.0
        assert to_float(None) == 0.0

    def test_to_float_default(self):
        assert to_float("", default=5.0) == 5.0

    def test_to_float_or_none(self):
        assert to_float_or_none("12.50") == 12.50
        assert to_float_or_none("") is None
        assert to_float_or_none(None) is None

    def test_to_int(self):
        assert to_int("5") == 5
        assert to_int("5.7") == 5
        assert to_int("") == 0

    def test_to_bool(self):
        assert to_bool("TRUE") is True
        assert to_bool("true") is True
        assert to_bool("1") is True
        assert to_bool("FALSE") is False
        assert to_bool("") is False
        assert to_bool(None) is False

    def test_fmt_bool(self):
        assert fmt_bool(True) == "TRUE"
        assert fmt_bool(False) == "FALSE"
