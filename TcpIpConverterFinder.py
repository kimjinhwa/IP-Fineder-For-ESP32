import tkinter as tk
from tkinter import ttk
import socket
import threading
import time
import json
import uuid

def normalize_mac(mac: str) -> str:
    if not mac:
        return ""
    return mac.strip().upper().replace("-", ":")

def mac_oui(mac: str) -> str:
    mac = normalize_mac(mac)
    parts = [p for p in mac.split(":") if p]
    if len(parts) < 3:
        return ""
    return ":".join(parts[:3])

OUI_NOTE_MAP = {
    # Raspberry Pi Foundation / Trading
    "B8:27:EB": "Raspberry Pi",
    "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi",
    "28:CD:C1": "Raspberry Pi",
    "88:A2:9E": "Raspberry Pi",

    # Espressif (ESP32/ESP8266)
    "24:6F:28": "ESP32",
    "30:AE:A4": "ESP32",
    "3C:71:BF": "ESP32",
    "7C:DF:A1": "ESP32",
    "7C:9E:BD": "ESP32",
    "84:F3:EB": "ESP32",
}

def get_note_for_mac(mac: str) -> str:
    return OUI_NOTE_MAP.get(mac_oui(mac), "")

class IPFinder:
    UDP_PORT = 1234  # 클래스 상단에 정의
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("IP Finder")
        self.root.geometry("600x400")

        # 상단 프레임
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=10)

        # IP 정보 입력 필드들 - VERSION 위치 변경
        labels = ['IPADDRESS', 'GATEWAY', 'SUBNET', 'MAC ADDR', 'VERSION']  # VERSION을 마지막으로 이동
        self.entries = {}
        
        for i, label in enumerate(labels):
            tk.Label(top_frame, text=f"{label} :").grid(row=i, column=0, padx=5, pady=2, sticky='e')
            entry = tk.Entry(top_frame, width=30)
            if label == 'VERSION':  # VERSION 필드는 읽기 전용으로 설정
                entry.configure(state='readonly')
            entry.grid(row=i, column=1, padx=5, pady=2)
            self.entries[label] = entry

        # 설정 버튼 위치 조정 (labels 개수가 바뀌지 않았으므로 row는 그대로)
        self.setup_btn = tk.Button(top_frame, text="설정", command=self.setup_address, width=10)
        self.setup_btn.grid(row=1, column=2, padx=10, pady=5)

        # 검색 버튼 위치 유지
        self.search_btn = tk.Button(top_frame, text="검색", command=self.search_devices, width=10)
        self.search_btn.grid(row=1, column=3, padx=10, pady=5)

        # 리스트박스 프레임
        list_frame = tk.Frame(self.root)
        list_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        # 컬럼 헤더
        self.tree = ttk.Treeview(list_frame, columns=('IP Address', 'MAC','NOTE'), show='headings')
        self.tree.heading('IP Address', text='IP Address')
        self.tree.heading('MAC', text='MAC')
        self.tree.heading('NOTE', text='NOTE')
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10)

        # UDP 소켓 설정
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(('', 0))  # 임의의 포트에 바인딩

        # 수신 스레드 시작
        self.running = True
        self.receiver_thread = threading.Thread(target=self.receive_responses)
        self.receiver_thread.daemon = True
        self.receiver_thread.start()

        # 트리뷰 선택 이벤트 바인딩
        self.tree.bind('<<TreeviewSelect>>', self.on_select)

        self.found_devices = set()

    def search_devices(self):
        # 리스트박스 클리어
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.found_devices.clear()

        # JSON 형식의 검색 메시지 생성 및 전송
        discovery_message = create_discovery_message()
        self.sock.sendto(discovery_message.encode(), ('255.255.255.255', self.UDP_PORT))

    def receive_responses(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                response = json.loads(data.decode())
                
                # JSON 응답 처리
                if response["cmd"] == "DEVICE_RESPONSE":
                    device = response["device"]
                    ip = device["network"]["ip"]
                    mac = device["mac"]
                    version = response.get("ver", "unknown")
                    hostname = response.get("hostname","")
                    note = hostname
                    
                    if ip not in self.found_devices:
                        self.found_devices.add(ip)
                        if(hostname==""):
                            note = get_note_for_mac(mac)
                        self.tree.insert('', 'end', values=(ip, mac, note))
                        
                        # 네트워크 정보가 있다면 저장
                        if device["network"].get("subnet"):
                            self.entries['SUBNET'].delete(0, tk.END)
                            self.entries['SUBNET'].insert(0, device["network"]["subnet"])
                        if device["network"].get("gateway"):
                            self.entries['GATEWAY'].delete(0, tk.END)
                            self.entries['GATEWAY'].insert(0, device["network"]["gateway"])
                            
                        # VERSION 정보 업데이트
                        self.entries['VERSION'].configure(state='normal')
                        self.entries['VERSION'].delete(0, tk.END)
                        self.entries['VERSION'].insert(0, version)
                        self.entries['VERSION'].configure(state='readonly')
                            
            except Exception as e:
                print(f"Error receiving response: {e}")
            time.sleep(0.1)

    def on_select(self, event):
        selected_item = self.tree.selection()
        if selected_item:
            item = self.tree.item(selected_item[0])
            values = item.get('values') or []
            ip = values[0] if len(values) > 0 else ""
            mac = values[1] if len(values) > 1 else ""
            # 선택된 항목의 정보를 상단 텍스트박스에 표시
            self.entries['IPADDRESS'].delete(0, tk.END)
            self.entries['IPADDRESS'].insert(0, ip)
            self.entries['MAC ADDR'].delete(0, tk.END)
            self.entries['MAC ADDR'].insert(0, mac)

    def setup_address(self):
        # 설정 버튼 클릭 시 처리
        mac = self.entries['MAC ADDR'].get()
        ip = self.entries['IPADDRESS'].get()
        subnet = self.entries['SUBNET'].get()
        gateway = self.entries['GATEWAY'].get()
        
        # JSON 형식의 설정 메시지 생성 및 전송
        config_message = create_config_message(mac, ip, subnet, gateway)
        self.sock.sendto(config_message.encode(), ('255.255.255.255', self.UDP_PORT))

    def run(self):
        self.root.mainloop()
        self.running = False

def generate_message_id():
    return str(uuid.uuid4())

def create_discovery_message():
    return json.dumps({
        "cmd": "DEVICE_DISCOVERY",
        "ver": "1.0",
        "msgId": generate_message_id(),
        "timestamp": int(time.time())
    })

def create_config_message(mac, ip, subnet, gateway):
    return json.dumps({
        "cmd": "SET_NETWORK_CONFIG",
        "ver": "1.0",
        "msgId": generate_message_id(),
        "timestamp": int(time.time()),
        "target": mac,
        "config": {
            "network": {
                "ip": ip,
                "subnet": subnet,
                "gateway": gateway
            }
        }
    })

if __name__ == "__main__":
    app = IPFinder()
    app.run()
