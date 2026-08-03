#!/usr/bin/env python3
"""
SAMUDRA RAKSHAK - BASE STATION (NETWORKED)
Raspberry Pi 4 with ADXL345 + LEDs
Sends data to cloud backend server
"""

import json
import csv
import socket
import threading
import time
import requests
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import RPi.GPIO as GPIO

# Try to import ADXL345 library
try:
    import board
    import busio
    import adafruit_adxl34x
    ADXL_AVAILABLE = True
except ImportError:
    ADXL_AVAILABLE = False
    print("⚠️  ADXL345 library not found")

# ==================== CONFIGURATION ====================
# Cloud backend server URL
BACKEND_URL = "http://YOUR_SERVER_IP:8000"  # CHANGE THIS!
# Example: "http://192.168.1.100:8000" for local network
# Example: "http://your-domain.com:8000" for cloud server

# TCP Configuration
LISTEN_IP = '0.0.0.0'
LISTEN_PORT = 5555
WEB_PORT = 8080

# Update interval (seconds)
UPDATE_INTERVAL = 5

# ==================== PIN DEFINITIONS ====================
LED_RED = 6
LED_GREEN = 13
LED_YELLOW = 19
LED_BLUE = 16

RGB_RED = 12
RGB_GREEN = 18
RGB_BLUE = 20

ADXL_INT1 = 4

# ==================== GLOBAL VARIABLES ====================
latest_packets = []
MAX_PACKETS = 100
csv_file = None
csv_writer = None
system_running = True
vibration_detected = False

# ==================== GPIO SETUP ====================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

led_pins = [LED_RED, LED_GREEN, LED_YELLOW, LED_BLUE, RGB_RED, RGB_GREEN, RGB_BLUE]
for pin in led_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

if ADXL_AVAILABLE:
    GPIO.setup(ADXL_INT1, GPIO.IN)

print("✓ GPIO initialized")

# ==================== LED CONTROL ====================
def led_on(pin):
    GPIO.output(pin, GPIO.HIGH)

def led_off(pin):
    GPIO.output(pin, GPIO.LOW)

def led_blink(pin, duration=0.1):
    led_on(pin)
    time.sleep(duration)
    led_off(pin)

def rgb_color(red, green, blue):
    GPIO.output(RGB_RED, GPIO.HIGH if red else GPIO.LOW)
    GPIO.output(RGB_GREEN, GPIO.HIGH if green else GPIO.LOW)
    GPIO.output(RGB_BLUE, GPIO.HIGH if blue else GPIO.LOW)

def rgb_off():
    rgb_color(0, 0, 0)

def rgb_status_normal():
    rgb_color(0, 1, 0)

def rgb_status_emergency():
    rgb_color(1, 0, 0)

def rgb_status_network():
    rgb_color(0, 0, 1)

# ==================== ADXL345 SETUP ====================
accelerometer = None

if ADXL_AVAILABLE:
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        accelerometer = adafruit_adxl34x.ADXL345(i2c, address=0x53)
        accelerometer.enable_motion_detection(threshold=18)
        print(f"✓ ADXL345 initialized")
    except Exception as e:
        print(f"✗ ADXL345 initialization failed: {e}")
        accelerometer = None

# ==================== CLOUD COMMUNICATION ====================
def send_to_cloud(endpoint, data):
    """Send data to cloud backend"""
    try:
        url = f"{BACKEND_URL}{endpoint}"
        response = requests.post(
            url,
            json=data,
            timeout=5,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            led_blink(LED_BLUE, 0.05)
            return True
        else:
            print(f"Cloud error: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("⚠️  Cannot connect to cloud server")
        led_blink(LED_RED, 0.1)
        return False
    except Exception as e:
        print(f"Cloud send error: {e}")
        return False

def cloud_update_thread():
    """Periodically send status updates to cloud"""
    global system_running
    
    print("✓ Cloud update thread started")
    
    while system_running:
        try:
            # Get accelerometer data
            accel_data = None
            if accelerometer:
                try:
                    x, y, z = accelerometer.acceleration
                    accel_data = {
                        'x': round(x, 2),
                        'y': round(y, 2),
                        'z': round(z, 2),
                        'magnitude': round((x**2 + y**2 + z**2) ** 0.5, 2)
                    }
                except:
                    pass
            
            # Prepare status update
            status = {
                'timestamp': datetime.now().isoformat(),
                'total_packets': len(latest_packets),
                'vibration_detected': vibration_detected,
                'accelerometer': accel_data,
                'port': LISTEN_PORT
            }
            
            # Send to cloud
            send_to_cloud('/api/base/data', status)
            
        except Exception as e:
            print(f"Cloud update error: {e}")
        
        time.sleep(UPDATE_INTERVAL)

# ==================== VIBRATION MONITORING ====================
def vibration_monitor_thread():
    global vibration_detected, system_running
    
    if not accelerometer:
        print("⚠️  Vibration monitoring disabled")
        return
    
    print("✓ Vibration monitoring started")
    
    while system_running:
        try:
            x, y, z = accelerometer.acceleration
            magnitude = (x**2 + y**2 + z**2) ** 0.5
            
            if magnitude > 12.0:
                vibration_detected = True
                print(f"⚠️  Vibration detected! {magnitude:.2f} m/s²")
                led_blink(LED_RED, 0.2)
            else:
                vibration_detected = False
            
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Vibration monitor error: {e}")
            time.sleep(1)

# ==================== TCP SERVER ====================
def tcp_server_thread():
    global latest_packets, csv_writer, csv_file
    
    # Open CSV file
    csv_file = open('vessel_data.csv', 'a', newline='')
    csv_writer = csv.writer(csv_file)
    
    if csv_file.tell() == 0:
        csv_writer.writerow([
            'timestamp', 'vessel_id', 'vessel_lat', 'vessel_lon', 'satellites',
            'temperature', 'pH', 'turbidity', 'accX', 'accY', 'accZ',
            'emergency', 'buoy_id', 'buoy_lat', 'buoy_lon', 'buoy_temp',
            'water_detected', 'vessel_rssi', 'vibration_alert'
        ])
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((LISTEN_IP, LISTEN_PORT))
    server_socket.listen(5)
    
    print(f"✓ TCP server listening on {LISTEN_IP}:{LISTEN_PORT}")
    led_on(LED_BLUE)
    
    while system_running:
        try:
            client_socket, client_address = server_socket.accept()
            print(f"✓ Connection from {client_address}")
            led_blink(LED_YELLOW, 0.1)
            
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True
            )
            client_thread.start()
            
        except Exception as e:
            print(f"Server error: {e}")
            led_blink(LED_RED, 0.5)

def handle_client(client_socket, client_address):
    global latest_packets, csv_writer
    
    buffer = ""
    
    try:
        while system_running:
            data = client_socket.recv(4096)
            if not data:
                break
            
            buffer += data.decode('utf-8')
            
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                
                if line.strip():
                    try:
                        packet = json.loads(line)
                        
                        packet['vibration_alert'] = vibration_detected
                        
                        # Store locally
                        latest_packets.append(packet)
                        if len(latest_packets) > MAX_PACKETS:
                            latest_packets.pop(0)
                        
                        # Visual feedback
                        led_blink(LED_YELLOW, 0.05)
                        
                        if packet.get('emergency'):
                            print(f"  🚨 EMERGENCY from {packet.get('id')}!")
                            led_on(LED_RED)
                            rgb_status_emergency()
                            time.sleep(0.5)
                            led_off(LED_RED)
                        else:
                            rgb_status_normal()
                        
                        # Log to CSV
                        csv_writer.writerow([
                            datetime.now().isoformat(),
                            packet.get('id'),
                            packet.get('lat'),
                            packet.get('lon'),
                            packet.get('sats'),
                            packet.get('temp'),
                            packet.get('pH'),
                            packet.get('turb'),
                            packet.get('accX'),
                            packet.get('accY'),
                            packet.get('accZ'),
                            packet.get('emergency'),
                            packet.get('buoy_id'),
                            packet.get('buoy_lat'),
                            packet.get('buoy_lon'),
                            packet.get('buoy_temp'),
                            packet.get('water_detected'),
                            packet.get('vessel_rssi'),
                            vibration_detected
                        ])
                        csv_file.flush()
                        
                        # Send to cloud
                        send_to_cloud('/api/vessel/data', packet)
                        
                        print(f"✓ Packet from {packet.get('id')} via {packet.get('buoy_id')}")
                        
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                        led_blink(LED_RED, 0.1)
    
    except Exception as e:
        print(f"Client handler error: {e}")
    finally:
        client_socket.close()
        print(f"✗ Connection closed from {client_address}")

# ==================== WEB DASHBOARD ====================
class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            accel_data = "N/A"
            if accelerometer:
                try:
                    x, y, z = accelerometer.acceleration
                    accel_data = f"X:{x:.2f} Y:{y:.2f} Z:{z:.2f} m/s²"
                except:
                    accel_data = "Error reading"
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Samudra Rakshak - Base Station</title>
                <meta http-equiv="refresh" content="5">
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                        color: #fff;
                        padding: 20px;
                    }}
                    .container {{ max-width: 1400px; margin: 0 auto; }}
                    .header {{
                        background: rgba(255,255,255,0.1);
                        backdrop-filter: blur(10px);
                        padding: 30px;
                        border-radius: 15px;
                        margin-bottom: 20px;
                    }}
                    .alert {{
                        background: rgba(231, 76, 60, 0.9);
                        padding: 20px;
                        border-radius: 10px;
                        margin: 20px 0;
                        font-weight: bold;
                        text-align: center;
                    }}
                    .stats {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                        gap: 15px;
                        margin-bottom: 20px;
                    }}
                    .stat-card {{
                        background: rgba(255,255,255,0.1);
                        padding: 20px;
                        border-radius: 15px;
                    }}
                    .stat-card h3 {{ font-size: 0.9em; opacity: 0.8; margin-bottom: 10px; }}
                    .stat-card .value {{ font-size: 2em; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🌊 Samudra Rakshak - Base Station</h1>
                        <p>Connected to Cloud: {BACKEND_URL}</p>
                    </div>
                    
                    <div class="alert">
                        📡 View full dashboard at: <a href="{BACKEND_URL.replace(':8000', ':3000')}" style="color: #fff;">{BACKEND_URL.replace(':8000', ':3000')}</a>
                    </div>
                    
                    <div class="stats">
                        <div class="stat-card">
                            <h3>📊 TOTAL PACKETS</h3>
                            <div class="value">{len(latest_packets)}</div>
                        </div>
                        <div class="stat-card">
                            <h3>🔌 PORT</h3>
                            <div class="value">{LISTEN_PORT}</div>
                        </div>
                        <div class="stat-card">
                            <h3>📡 ACCELEROMETER</h3>
                            <div class="value" style="font-size: 1em;">{accel_data}</div>
                        </div>
                        <div class="stat-card">
                            <h3>🕐 LAST UPDATE</h3>
                            <div class="value" style="font-size: 1.2em;">{datetime.now().strftime('%H:%M:%S')}</div>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        pass

# ==================== MAIN ====================
def main():
    global system_running
    
    print("\n╔═══════════════════════════════════════════════╗")
    print("║  SAMUDRA RAKSHAK - BASE STATION (NETWORKED)  ║")
    print("╚═══════════════════════════════════════════════╝\n")
    
    # Validate backend URL
    if "YOUR_SERVER_IP" in BACKEND_URL:
        print("❌ ERROR: Please set BACKEND_URL in the code!")
        print("   Change YOUR_SERVER_IP to your actual server IP")
        return
    
    # Start vibration monitoring
    if accelerometer:
        vib_thread = threading.Thread(target=vibration_monitor_thread, daemon=True)
        vib_thread.start()
    
    # Start TCP server
    tcp_thread = threading.Thread(target=tcp_server_thread, daemon=True)
    tcp_thread.start()
    
    # Start cloud updates
    cloud_thread = threading.Thread(target=cloud_update_thread, daemon=True)
    cloud_thread.start()
    
    time.sleep(1)
    
    # Start web server
    server = HTTPServer(('0.0.0.0', WEB_PORT), DashboardHandler)
    
    print(f"\n✓ System ready!")
    print(f"✓ Local dashboard: http://localhost:{WEB_PORT}")
    print(f"✓ Cloud backend: {BACKEND_URL}")
    print(f"✓ TCP server: Port {LISTEN_PORT}")
    print("\nPress Ctrl+C to stop\n")
    
    led_on(LED_GREEN)
    rgb_status_normal()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n✓ Shutting down...")
        system_running = False
        time.sleep(1)
        
        for pin in led_pins:
            led_off(pin)
        
        GPIO.cleanup()
        
        if csv_file:
            csv_file.close()
        
        server.shutdown()
        print("✓ Shutdown complete")

if __name__ == "__main__":
    main()
