def test_ci_must_turn_red() -> None:
    # Deliberately failing, to see "CI ok" go red on GitHub; reverted by the next commit.
    assert 1 == 2  # noqa: PLR0133
