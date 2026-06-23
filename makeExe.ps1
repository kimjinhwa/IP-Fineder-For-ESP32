# pip install pyinstaller
# pyinstaller --onefile --windowed TcpIpConverterFinder.py

#pyinstaller --onefile --windowed   --icon=iftech_logo.ico --name=IPFinder_v1.1.1 TcpIpConverterFinder.py

pyinstaller --noconfirm --onefile --windowed --icon=iftech_logo.ico --add-data "iftech_logo.ico;." --name=IPFinder_v1.1.1 TcpIpConverterFinder.py
# pyinstaller --onefile --name=IPFinder --icon=icon.ico TcpIpConverterFinder.py
