import requests

def arp(ip=None):
    try:
        self_check = False
        if not ip:
            self_check = True
            ip = requests.get("https://ifconfig.me").text.strip()
        geo_response = requests.get(f"http://ip-api.com/json/{ip}")
        geo_response.raise_for_status()
        geo_data = geo_response.json()

        if geo_data["status"] == "success":
            country = geo_data["countryCode"]
            if country == "RU":
                return True
            if self_check:
                print(f"Your public IP address: {ip}")
            return False
        else:
            if self_check:
                print("Failed to retrieve ip information, meaning local network access. Exiting.")
                quit()
            else:
                print(f"Local network connection from {ip}")

    except requests.RequestException as e:
        print(f"Network error: {e}")
        quit()