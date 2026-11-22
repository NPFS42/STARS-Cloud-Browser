import pytest
from browser_control.security import validate_target, UnsafeURL, issue_session, verify_session, check_configuration

@pytest.mark.parametrize('url', [
  'http://127.0.0.1/', 'http://10.10.1.1/', 'http://100.100.100.100/',
  'http://169.254.169.254/latest/meta-data', 'http://[::1]/',
  'http://localhost/', 'https://router.local/', 'https://device.ts.net/',
  'file:///etc/passwd', 'javascript:alert(1)', 'http://user:pass@example.com/',
  'https://example.com:8765/','http://192.168.1.1/'
])
def test_rejects_private_destinations(url):
    with pytest.raises(UnsafeURL): validate_target(url,resolve=False)

@pytest.mark.parametrize('url', ['https://example.com/','http://93.184.215.14/','https://example.org/path?q=1'])
def test_public_shape_ok(url):
    assert validate_target(url,resolve=False)==url

def test_dns_rebinding_is_rejected(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(None,None,None,None,('10.0.0.5',443))])
    with pytest.raises(UnsafeURL):validate_target('https://example.net')

def test_fails_closed_on_dns_error(monkeypatch):
    import socket
    def nope(*a,**kw): raise OSError('no DNS')
    monkeypatch.setattr(socket,'getaddrinfo',nope)
    with pytest.raises(UnsafeURL):validate_target('https://example.net')

def test_session_is_integrity_protected():
    token=issue_session('a'*48)
    assert verify_session(token,'a'*48)
    assert not verify_session(token,'b'*48)
    assert not verify_session(token+'x','a'*48)
    assert not verify_session(None,'a'*48)

def test_config_requires_two_secrets(monkeypatch):
    monkeypatch.setenv('STARS_BROWSER_UI_SECRET','x'*48)
    monkeypatch.setenv('STARS_BROWSER_MCP_TOKEN','x'*48)
    monkeypatch.setenv('STARS_BROWSER_ALLOWED_HOST','a.ts.net')
    with pytest.raises(RuntimeError):check_configuration()
    monkeypatch.setenv('STARS_BROWSER_MCP_TOKEN','y'*48)
    check_configuration()
