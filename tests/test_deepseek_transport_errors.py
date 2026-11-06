"""Transport diagnostics reveal a fixed category, never request/key/URL text."""
import errno
import json
import socket
import ssl
from urllib.error import URLError
from unittest.mock import Mock, patch

import pytest

from app.services.llm.deepseek_provider import BudgetLedger, DeepSeekDemoProvider, SpikeError


@pytest.mark.parametrize('reason, expected', [
    (socket.gaierror(-2, 'secret-host-and-credential'), 'TRANSPORT_DNS'),
    (ssl.SSLCertVerificationError(1, 'secret-host-and-credential'), 'TRANSPORT_TLS_CERTIFICATE'),
    (ssl.SSLError(1, 'secret-host-and-credential'), 'TRANSPORT_TLS'),
    (TimeoutError('secret-host-and-credential'), 'TRANSPORT_TIMEOUT'),
    (ConnectionRefusedError(errno.ECONNREFUSED, 'secret-host-and-credential'), 'TRANSPORT_CONNECTION_REFUSED'),
    (ConnectionResetError(errno.ECONNRESET, 'secret-host-and-credential'), 'TRANSPORT_CONNECTION_RESET'),
    (OSError(errno.ENETUNREACH, 'secret-host-and-credential'), 'TRANSPORT_NETWORK_UNREACHABLE'),
    ('https://secret-host-and-credential', 'TRANSPORT_UNKNOWN'),
])
def test_provider_saves_safe_transport_category_once(tmp_path, monkeypatch, reason, expected):
    monkeypatch.setenv('MRA_ANONYMIZE', '1')
    monkeypatch.setenv('MEDICAL_RECORD_AGENT_DB', str(tmp_path / 'identity.sqlite3'))
    provider = DeepSeekDemoProvider(api_key='never-print-this-key', output=tmp_path / 'diagnostics',
        ledger=BudgetLedger(tmp_path / 'ledger.json'))
    opener = Mock()
    opener.open.side_effect = URLError(reason)
    with patch('app.services.llm.deepseek_provider.request.build_opener', return_value=opener):
        with pytest.raises(SpikeError, match='^' + expected + '$'):
            provider.generate_fields_json('患者：发热。', timeout_seconds=1)
    assert opener.open.call_count == 1
    failure = json.loads(next((tmp_path / 'diagnostics').glob('*/failure.json')).read_text())
    assert failure['code'] == expected and failure['auto_retry'] is False
    ledger = json.loads((tmp_path / 'ledger.json').read_text())
    assert len(ledger['calls']) == 1
    assert ledger['calls'][0]['state'] == 'failed_reservation_retained'
    all_json = '\n'.join(path.read_text(encoding='utf-8') for path in tmp_path.rglob('*.json'))
    assert 'never-print-this-key' not in all_json
    assert 'secret-host-and-credential' not in all_json
