import socket

import psutil


def get_lan_addresses():
    """Return usable IPv4 addresses for LAN clients to connect to."""
    results = []
    for interface, addresses in psutil.net_if_addrs().items():
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            ip = address.address
            if ip.startswith(("127.", "169.254.")):
                continue
            results.append({"interface": interface, "ipv4": ip})
    return results
