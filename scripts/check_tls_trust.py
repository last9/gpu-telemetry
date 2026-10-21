#!/usr/bin/env python3
"""Check eMudhra rejection and trusted HTTPS using real TLS handshakes."""

import argparse
import socket
import ssl

import certifi


def check_context(label: str, context: ssl.SSLContext) -> bool:
    success = True
    for host, should_trust in (
        ("example.com", True),
        ("dv-g3b-emudhra.we-have-a-problem.com", False),
        ("dv-g3b-aaa-emudhra.we-have-a-problem.com", False),
    ):
        try:
            with socket.create_connection((host, 443), timeout=15) as connection:
                with context.wrap_socket(connection, server_hostname=host):
                    pass
        except ssl.SSLCertVerificationError as error:
            if should_trust:
                print(f"FAIL {label}: {host}: {error}")
                success = False
            else:
                print(f"PASS {label}: rejected {host}: {error.verify_message}")
        except OSError as error:
            # DNS failures, timeouts, and connection errors are inconclusive.
            print(f"FAIL {label}: {host}: {error}")
            success = False
        else:
            if should_trust:
                print(f"PASS {label}: trusted {host}")
            else:
                print(f"FAIL {label}: trusted compromised chain for {host}")
                success = False
    return success


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--system", action="store_true", help="also check the system CA bundle"
    )
    args = parser.parse_args()
    success = check_context(
        f"certifi {certifi.__version__}",
        ssl.create_default_context(cafile=certifi.where()),
    )
    if args.system:
        success = check_context("system", ssl.create_default_context()) and success
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
