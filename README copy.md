# JEA-Shell

A Kerberos-authenticated WinRM shell for interacting with Windows endpoints — including **JEA (Just Enough Administration)** restricted sessions running in **ConstrainedLanguageMode (CLM)**.

## Features

- Kerberos authentication via ccache (pass-the-ticket, no password needed)
- Full unrestricted PowerShell sessions
- JEA restricted endpoint support
- CLM-compatible file reading using PowerShell's variable-provider syntax (`${C:\path}`)
- PSReadLine history dumping
- Interactive pseudo-shell

## Requirements

- Linux / Exegol (uses `gssapi` + MIT Kerberos)
- Python 3.10+
- `pypsrp`, `gssapi`

```bash
pip install pypsrp gssapi
# or
poetry install
```

## Setup

1. Copy `krb5.conf.example` to `/etc/krb5.conf` (or any path) and adjust realm/KDC.
2. Obtain a Kerberos ccache (e.g. via `getTGT.py`, `certipy`, or `impacket`).

## Usage

```
python jea_shell.py --host <HOST> --ccache <CCACHE> [--krb5 <KRB5_CONF>] [--endpoint <JEA_NAME>] [ACTION]
```

### Connection options

| Flag | Default | Description |
|---|---|---|
| `--host` | *(required)* | Target hostname |
| `--ccache` | *(required)* | Path to Kerberos ccache file |
| `--krb5` | `/etc/krb5.conf` | Path to krb5.conf |
| `--endpoint` | *(none)* | JEA configuration name (omit for full PS) |
| `--port` | `5985` | WinRM port |
| `--ssl` | off | Use HTTPS (auto-switches to 5986) |

### Actions

| Flag | Description |
|---|---|
| `--whoami` | Print current identity |
| `--jea-commands` | List available commands in the JEA endpoint |
| `--exec "SCRIPT"` | Run a single PowerShell script |
| `--history USER…` | Dump PSReadLine history for one or more users |
| `--read PATH` | Read a remote file |
| `--ls PATH` | List a remote directory |
| `--shell` | Drop into an interactive pseudo-shell |

### Examples

```bash
# Full PS session — check identity
python jea_shell.py --host dc1.corp.local --ccache admin.ccache --whoami

# Full PS session — interactive shell
python jea_shell.py --host dc1.corp.local --ccache admin.ccache --shell

# JEA session — list allowed commands
python jea_shell.py --host dc1.corp.local --ccache svc.ccache --endpoint restricted --jea-commands

# JEA/CLM session — read a file (uses variable-provider syntax internally)
python jea_shell.py --host dc1.corp.local --ccache svc.ccache --endpoint restricted --read 'C:\Users\Administrator\secret.txt'

# JEA/CLM session — dump PSReadLine history
python jea_shell.py --host dc1.corp.local --ccache svc.ccache --endpoint restricted --history Administrator svc_backup

# Custom krb5.conf + HTTPS
python jea_shell.py --host dc1.corp.local --ccache admin.ccache --krb5 /tmp/corp.conf --ssl --whoami
```

## JEA / CLM notes

When `--endpoint` is set, the session is assumed to be a JEA endpoint running in ConstrainedLanguageMode. In this mode:

- `Get-Content`, `Get-ChildItem`, and most cmdlets may be blocked by the JEA whitelist.
- .NET method calls (`[System.IO.File]::ReadAllText()`) are blocked by CLM.
- `$ExecutionContext.InvokeProvider` methods are also blocked.

**Working bypass:** PowerShell's variable-provider syntax `${C:\path\to\file}` reads file content directly through the FileSystem provider at the language level, bypassing both cmdlet whitelisting and CLM restrictions.
