import socket
import json
import time
import sys
import fcntl
import struct
import subprocess

# 설정
UDP_IP = "0.0.0.0"
UDP_PORT = 1234
VERSION = "1.0"


def get_host_name():
    hostname = subprocess.check_output(["hostname"]).decode("utf-8").strip()
    print(f"System Hostname: {hostname}")
    return hostname


def get_active_ethernet_info():
    """nmcli를 통해 활성화된 이더넷 정보를 가져옵니다."""
    try:
        output = subprocess.check_output(
            "nmcli -t -f NAME,TYPE,DEVICE,STATE connection show --active",
            shell=True,
        ).decode("utf-8")

        for line in output.split("\n"):
            if "802-3-ethernet" in line and ":activated" in line:
                parts = line.split(":")
                return {
                    "profile": parts[0],
                    "device": parts[2],
                }
    except Exception as e:
        print(f"Error finding active ethernet: {e}")

    return {"profile": "managed-eth0", "device": "eth0"}


NET_INFO = get_active_ethernet_info()
TARGET_PROFILE = NET_INFO["profile"]
TARGET_IFACE = NET_INFO["device"]

print(f"Detected Interface: {TARGET_IFACE}")
print(f"Detected Profile: {TARGET_PROFILE}")


def set_static_ip(ifname, ip, subnet, gateway):
    """NetworkManager(nmcli)를 사용하여 고정 IP를 설정합니다."""
    try:

        def mask_to_cidr(mask):
            return sum(bin(int(x)).count("1") for x in mask.split("."))

        cidr = mask_to_cidr(subnet)
        ip_with_cidr = f"{ip}/{cidr}"

        print(f"Applying Static IP: {ip_with_cidr}, GW: {gateway} on {ifname}")

        cmds = [
            f"sudo nmcli device modify {ifname} ipv4.addresses {ip_with_cidr} ipv4.gateway {gateway} ipv4.method manual"
        ]
        print(cmds)
        for cmd in cmds:
            subprocess.run(cmd, shell=True, check=True)

        return True
    except Exception as e:
        print(f"Failed to set IP: {e}")
        return False


def get_net_info(ifname):
    """특정 인터페이스의 IP와 Subnet Mask를 가져옵니다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = {"ip": "0.0.0.0", "subnet": "0.0.0.0"}
    try:
        info["ip"] = socket.inet_ntoa(
            fcntl.ioctl(
                s.fileno(),
                0x8915,
                struct.pack("256s", ifname[:15].encode("utf-8")),
            )[20:24]
        )
        info["subnet"] = socket.inet_ntoa(
            fcntl.ioctl(
                s.fileno(),
                0x891b,
                struct.pack("256s", ifname[:15].encode("utf-8")),
            )[20:24]
        )
    except OSError:
        pass
    finally:
        s.close()
    return info


def get_gateway():
    try:
        with open("/proc/net/route") as f:
            for line in f:
                fields = line.strip().split()
                if fields[1] == "00000000":
                    return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    except OSError:
        return "0.0.0.0"
    return "0.0.0.0"


def get_mac_address(ifname):
    try:
        with open(f"/sys/class/net/{ifname}/address") as f:
            return f.read().strip().upper()
    except OSError:
        return "00:00:00:00:00:00"


def broadcast_reply_dest(addr):
    """
    PC가 다른 서브넷에 있어도 같은 L2에서는 유니캐스트 응답이 안 돌아올 수 있음.
    브로드캐스트 + 요청자의 UDP 소스 포트로 보내면 PC의 recvfrom 소켓으로 들어감.
    """
    return ("255.255.255.255", addr[1])


def run_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((UDP_IP, UDP_PORT))

    print(f"UDP Service started. Monitoring {TARGET_IFACE}...", flush=True)
    start_time = time.time()

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            incoming_packet = data.decode("utf-8").strip()

            try:
                doc_rx = json.loads(incoming_packet)
                if doc_rx.get("cmd") == "SET_NETWORK_CONFIG":
                    print(doc_rx, flush=True)
                    target_mac = doc_rx.get("target")
                    my_mac = get_mac_address(TARGET_IFACE)

                    if target_mac.upper() == my_mac.upper():
                        net_cfg = doc_rx.get("config", {}).get("network", {})
                        new_ip = net_cfg.get("ip")
                        new_subnet = net_cfg.get("subnet")
                        new_gateway = net_cfg.get("gateway")

                        success = set_static_ip(
                            TARGET_IFACE, new_ip, new_subnet, new_gateway
                        )
                        response = {
                            "cmd": "NETWORK_CONFIG_RESPONSE",
                            "ver": "1.0",
                            "msgId": doc_rx.get("msgId"),
                            "status": "success" if success else "fail",
                            "message": (
                                "Network config applied. System may reconnect."
                                if success
                                else "Failed to apply config"
                            ),
                        }
                        sock.sendto(
                            json.dumps(response).encode("utf-8"),
                            broadcast_reply_dest(addr),
                        )
                        print(response)

                        if success:
                            print("Network configuration changed successfully.")
                if doc_rx.get("cmd") == "DEVICE_DISCOVERY":
                    print(doc_rx, flush=True)
                    net_info = get_net_info(TARGET_IFACE)

                    response = {
                        "cmd": "DEVICE_RESPONSE",
                        "ver": VERSION,
                        "msgId": doc_rx.get("msgId"),
                        "device": {
                            "type": "RPi_Node",
                            "mac": get_mac_address(TARGET_IFACE),
                            "network": {
                                "ip": net_info["ip"],
                                "subnet": net_info["subnet"],
                                "gateway": get_gateway(),
                            },
                            "status": "active",
                            "uptime": int(time.time() - start_time),
                        },
                        "hostname": get_host_name(),
                    }
                    sock.sendto(
                        json.dumps(response).encode("utf-8"),
                        broadcast_reply_dest(addr),
                    )
            except json.JSONDecodeError as je:
                print(
                    f"JSON Decode Error: {je} | Data: {incoming_packet}",
                    flush=True,
                )
            except Exception as e:
                print(f"Internal Logic Error: {e}", flush=True)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)

        time.sleep(0.1)


if __name__ == "__main__":
    run_server()
