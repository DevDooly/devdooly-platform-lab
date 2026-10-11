"""Generate checkout-local Compose secrets without printing their values."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[2]
destination = root / '.local' / 'compose.env'
destination.parent.mkdir(parents=True, exist_ok=True)
if destination.exists():
    print('Existing .local/compose.env preserved.')
else:
    content = '\n'.join([
        'MARIADB_ROOT_PASSWORD=' + secrets.token_urlsafe(32),
        'MARIADB_PASSWORD=' + secrets.token_urlsafe(32),
        'LAB_BIND_HOST=127.0.0.1',
        'LAB_HTTP_PORT=4310',
        'SOURCE_COMMIT=unknown',
        '',
    ])
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
    destination.chmod(0o600)
    print('Created .local/compose.env. Password values were not printed.')
