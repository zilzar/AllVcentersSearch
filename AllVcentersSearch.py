import sys
import json
import ssl
import datetime
import time
import threading
from PyQt5 import QtWidgets
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from prettytable import PrettyTable

def keep_alive(si, interval=600):
    def keep_alive_thread():
        while True:
            try:
                si.CurrentTime()
            except Exception as e:
                print(f"Keep-alive Failed: {e}")
            time.sleep(interval)
    
    threading.Thread(target=keep_alive_thread, daemon=True).start()

def connect_to_vcenter(host, user, pwd):
    try:
        context = ssl._create_unverified_context()
        si = SmartConnect(host=host, user=user, pwd=pwd, sslContext=context)
        
        keep_alive(si)

        return si
    except vim.fault.InvalidLogin:
        print(f"Cannot connect to {host}: Incorrect username or password.")
        return None
    except Exception as e:
        print(f"Could not connect to {host}: {e}")
        return None

def get_vcenter_connections(user, pwd):
    with open("VCENTERLAR.json", "r") as file:
        credentials = json.load(file)
    
    connections = []
    failed_connections = []

    for vc in credentials["vcenters"]:
        host = vc["host"]
        si = connect_to_vcenter(host, user, pwd)
        if si:
            connections.append((host, si))
        else:
            failed_connections.append(host)

    if failed_connections:
        print("\nUnable to connect servers:")
        for host in failed_connections:
            print(f"- {host}")
    
    if connections:
        print("\nSearch the following servers:")
        for host, _ in connections:
            print(f"- {host}")
    else:
        print("Could not connect to any server, program is terminating.")
        sys.exit()

    return connections

def get_vm_info(vm, vc_host):
    ip_addresses = "\n".join(
        [ip for net in vm.guest.net for ip in net.ipAddress if ip and not ip.startswith("fe80")]
    ) if vm.guest.net else "Not Found"

    vm_info = {
        "vCenter": vc_host,
        "VM Name": vm.name,
        "VM Path": vm.summary.config.vmPathName,
        "Network": ", ".join([net.name for net in vm.network]) if vm.network else "N/A",
        "CPU": vm.config.hardware.numCPU,
        "RAM (GB)": vm.config.hardware.memoryMB // 1024,
        "HDD (GB)": sum([disk.capacityInKB for disk in vm.config.hardware.device if isinstance(disk, vim.vm.device.VirtualDisk)]) // (1024 * 1024),
        "IP Addresses": ip_addresses,
        "Power State": "ON" if vm.runtime.powerState == "poweredOn" else "OFF"
    }
    return vm_info

def search_vms_by_name(vm_name, connections):
    results = []

    for vc_host, si in connections:
        try:
            content = si.RetrieveContent()
            container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
            for vm in container.view:
                if vm_name.lower() in vm.name.lower():
                    results.append(get_vm_info(vm, vc_host))
            container.Destroy()
        except vim.fault.NotAuthenticated:
            print(f"Session expired, reconnecting to server {vc_host}...")
            si = connect_to_vcenter(vc_host, user, pwd)
            connections.append((vc_host, si))
        
    return results

def get_credentials():
    app = QtWidgets.QApplication(sys.argv)

    dialog = QtWidgets.QDialog()
    dialog.setWindowTitle("vCenter Login")

    layout = QtWidgets.QFormLayout()

    user_input = QtWidgets.QLineEdit()
    user_input.setPlaceholderText("vCenter UserName")
    pwd_input = QtWidgets.QLineEdit()
    pwd_input.setPlaceholderText("vCenter Password")
    pwd_input.setEchoMode(QtWidgets.QLineEdit.Password)

    layout.addRow("User Name:", user_input)
    layout.addRow("Password:", pwd_input)

    button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    layout.addWidget(button_box)
    dialog.setLayout(layout)

    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        user = user_input.text()
        pwd = pwd_input.text()
        if not user or not pwd:
            QtWidgets.QMessageBox.critical(None, "Error", "No username or password entered!")
            sys.exit()
        return user, pwd
    else:
        sys.exit()

def main():

    print("M.G.")
    
    user, pwd = get_credentials()

    connections = get_vcenter_connections(user, pwd)

    while True:
        search_term = input("Enter VM name or a value that contains: ")

        if len(search_term) < 3:
            print("Search term must be at least 3 characters. Please try again.")
            continue

        results = search_vms_by_name(search_term, connections)

        if results:
            table = PrettyTable()
            table.field_names = ["vCenter", "VM Name", "VM Path", "Network", "CPU", "RAM (GB)", "HDD (GB)", "IP Addresses", "Power State"]

            for result in results:
                table.add_row([
                    result["vCenter"],
                    result["VM Name"],
                    result["VM Path"],
                    result["Network"],
                    result["CPU"],
                    result["RAM (GB)"],
                    result["HDD (GB)"],
                    result["IP Addresses"],
                    result["Power State"]
                ])

            print(table)
        else:
            print("No results found.")

if __name__ == "__main__":
    main()
