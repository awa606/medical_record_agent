from scripts.check_docker_port import (
    PortCheckResult,
    is_port_excluded,
    parse_excluded_ranges,
    print_scan_result,
    scan_ports,
)


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


def test_scan_ports_recommends_first_bindable(monkeypatch):
    def fake_check_port(port: int) -> PortCheckResult:
        return PortCheckResult(
            port=port,
            bindable=port == 2644,
            excluded=port < 2644,
            reason="fake",
        )

    monkeypatch.setattr("scripts.check_docker_port.check_port", fake_check_port)

    result = scan_ports(2642, 2645)

    assert result.recommended_port == 2644
    assert [item.port for item in result.checked] == [2642, 2643, 2644, 2645]


def test_print_scan_result_env_outputs_mra_host_port(monkeypatch, capsys):
    def fake_check_port(port: int) -> PortCheckResult:
        return PortCheckResult(port=port, bindable=port == 2644, excluded=False, reason="fake")

    monkeypatch.setattr("scripts.check_docker_port.check_port", fake_check_port)

    print_scan_result(scan_ports(2643, 2644), "env")

    assert capsys.readouterr().out.strip() == "MRA_HOST_PORT=2644"
