from scripts.check_docker_port import is_port_excluded, parse_excluded_ranges


def test_parse_excluded_ranges_from_netsh_output():
    output = """
Protocol tcp Port Exclusion Ranges

Start Port    End Port
----------    --------
      2526        2625
     50000       50059     *
"""

    assert parse_excluded_ranges(output) == [(2526, 2625), (50000, 50059)]


def test_is_port_excluded_matches_range_boundaries():
    ranges = [(2526, 2625)]

    assert is_port_excluded(2601, ranges)
    assert is_port_excluded(2526, ranges)
    assert is_port_excluded(2625, ranges)
    assert not is_port_excluded(2626, ranges)
