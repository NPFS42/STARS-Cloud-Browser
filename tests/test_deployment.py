from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_docker_host_binding_loopback_only():
    compose=(ROOT/'compose.yaml').read_text()
    assert '127.0.0.1:8811:8811' in compose
    assert 'privileged: true' not in compose
    assert '/var/run/docker.sock' not in compose
    assert 'no-new-privileges:true' in compose
    assert 'read_only: true' in compose

def test_no_committed_secrets():
    example=(ROOT/'.env.example').read_text()
    assert 'REPLACE_WITH' in example
    assert not (ROOT/'.env').exists()
