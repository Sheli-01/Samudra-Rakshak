#!/usr/bin/env python3
"""
Floating Buoy System - NETWORKED VERSION
Raspberry Pi 3B + 2x LoRa (SX1278) + GPS (NEO-6M)
Sends status updates to cloud backend
"""

import time
import json
import logging
import requests
from datetime import datetime
import RPi.GPIO as GPIO
import serial
import pynmea2
from sx127x_gs import SX127x

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/buoy.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
# Cloud backend server URL
BACKEND_URL = "http://YOUR_SERVER_IP:8000"  # CHANGE THIS!

# LoRa Radio 1 (RX from vessels)
LORA1_CONFIG = {
    'spi_bus': 0,
    'spi_cs': 0,
    'pin_cs': 8,
    'pin_reset': 22,
    'pin_dio0': 17,
    'pin_dio1': 27,
    'frequency': 433.0,
    'tx_power': 17,
    'spreading_factor': 7,
    'bandwidth': 125000,
    'coding_rate': 5,
    'preamble_length': 8,
    'sync_word': 0x12
}

# LoRa Radio 2 (TX to base station)
LORA2_CONFIG = {
    'spi_bus': 1,
    'spi_cs': 0,
    'pin_cs': 7,
    'pin_reset': 25,
    'pin_dio0': 23,
    'pin_dio1': 24,
    'frequency': 433.5,
    'tx_power': 20,
    'spreading_factor': 8,
    'bandwidth': 125000,
    'coding_rate': 5,
    'preamble_length': 8,
    'sync_word': 0x34
}

# GPS Configuration
GPS_PORT = '/dev/serial0'
GPS_BAUDRATE = 9600
GPS_TIMEOUT = 1

BUOY_ID = "BUOY_001"
CLOUD_UPDATE_INTERVAL = 10  # seconds

# ==================== GPS HANDLER ====================
class GPSHandler:
    def __init__(self):
        self.serial = None
        self.last_valid_position = None
        self.last_valid_time = None
        
    def initialize(self):
        try:
            self.serial = serial.Serial(
                GPS_PORT,
                baudrate=GPS_BAUDRATE,
                timeout=GPS_TIMEOUT
            )
            logger.info("GPS initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize GPS: {e}")
            return False
    
    def read_position(self):
        if not self.serial:
            return None
        
        try:
            line = self.serial.readline().decode('ascii', errors='replace')
            
            if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                msg = pynmea2.parse(line)
                
                if msg.gps_qual > 0:
                    position = {
                        'latitude': msg.latitude,
                        'longitude': msg.longitude,
                        'altitude': msg.altitude,
                        'num_sats': msg.num_sats,
                        'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                        'quality': msg.gps_qual
                    }
                    self.last_valid_position = position
                    self.last_valid_time = time.time()
                    return position
                    
        except (pynmea2.ParseError, UnicodeDecodeError, AttributeError):
            pass
        except Exception as e:
            logger.error(f"GPS read error: {e}")
        
        if self.last_valid_position and (time.time() - self.last_valid_time) < 30:
            return self.last_valid_position
        
        return None
    
    def close(self):
        if self.serial:
            self.serial.close()

# ==================== LORA COMMUNICATION ====================
class LoRaCommunicator:
    def __init__(self):
        self.lora_rx = None
        self.lora_tx = None
        
    def initialize(self):
        try:
            logger.info("Initializing LoRa Radio 1 (RX)...")
            self.lora_rx = SX127x(
                spi_bus=LORA1_CONFIG['spi_bus'],
                spi_cs=LORA1_CONFIG['spi_cs'],
                pin_reset=LORA1_CONFIG['pin_reset'],
                pin_dio0=LORA1_CONFIG['pin_dio0']
            )
            self._configure_lora(self.lora_rx, LORA1_CONFIG)
            self.lora_rx.set_mode_rx_continuous()
            logger.info("LoRa Radio 1 initialized")
            
            logger.info("Initializing LoRa Radio 2 (TX)...")
            self.lora_tx = SX127x(
                spi_bus=LORA2_CONFIG['spi_bus'],
                spi_cs=LORA2_CONFIG['spi_cs'],
                pin_reset=LORA2_CONFIG['pin_reset'],
                pin_dio0=LORA2_CONFIG['pin_dio0']
            )
            self._configure_lora(self.lora_tx, LORA2_CONFIG)
            self.lora_tx.set_mode_standby()
            logger.info("LoRa Radio 2 initialized")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize LoRa: {e}")
            return False
    
    def _configure_lora(self, lora, config):
        lora.set_frequency(config['frequency'])
        lora.set_tx_power(config['tx_power'])
        lora.set_spreading_factor(config['spreading_factor'])
        lora.set_bandwidth(config['bandwidth'])
        lora.set_coding_rate(config['coding_rate'])
        lora.set_preamble_length(config['preamble_length'])
        lora.set_sync_word(config['sync_word'])
        lora.set_crc_on(True)
    
    def receive_from_vessel(self, timeout=1.0):
        if not self.lora_rx:
            return None
        
        try:
            if self.lora_rx.get_irq_flags()['rx_done']:
                payload = self.lora_rx.read_payload()
                rssi = self.lora_rx.get_packet_rssi()
                snr = self.lora_rx.get_packet_snr()
                
                self.lora_rx.clear_irq_flags()
                self.lora_rx.set_mode_rx_continuous()
                
                try:
                    message = payload.decode('utf-8')
                    data = json.loads(message)
                    data['rssi'] = rssi
                    data['snr'] = snr
                    return data
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.warning(f"Failed to decode vessel message: {e}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error receiving from vessel: {e}")
            
        return None
    
    def transmit_to_base(self, data):
        if not self.lora_tx:
            return False
        
        try:
            message = json.dumps(data)
            payload = message.encode('utf-8')
            
            self.lora_tx.set_mode_standby()
            self.lora_tx.write_payload(payload)
            self.lora_tx.set_mode_tx()
            
            start_time = time.time()
            while not self.lora_tx.get_irq_flags()['tx_done']:
                if time.time() - start_time > 5.0:
                    logger.warning("TX timeout")
                    break
                time.sleep(0.01)
            
            self.lora_tx.clear_irq_flags()
            self.lora_tx.set_mode_standby()
            
            logger.info(f"Transmitted to base: {message[:100]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error transmitting to base: {e}")
            return False
    
    def cleanup(self):
        if self.lora_rx:
            self.lora_rx.set_mode_sleep()
        if self.lora_tx:
            self.lora_tx.set_mode_sleep()

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
            logger.debug("Cloud update successful")
            return True
        else:
            logger.warning(f"Cloud error: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.warning("Cannot connect to cloud server")
        return False
    except Exception as e:
        logger.error(f"Cloud send error: {e}")
        return False

# ==================== BUOY SYSTEM ====================
class BuoySystem:
    def __init__(self):
        self.gps = GPSHandler()
        self.lora = LoRaCommunicator()
        self.running = False
        self.message_count = 0
        self.last_cloud_update = time.time()
        
    def initialize(self):
        logger.info("=" * 60)
        logger.info(f"Initializing Buoy System: {BUOY_ID}")
        logger.info("=" * 60)
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        if not self.gps.initialize():
            logger.error("GPS initialization failed")
            return False
        
        if not self.lora.initialize():
            logger.error("LoRa initialization failed")
            return False
        
        # Validate backend URL
        if "YOUR_SERVER_IP" in BACKEND_URL:
            logger.error("Please set BACKEND_URL in the code!")
            return False
        
        logger.info(f"Cloud backend: {BACKEND_URL}")
        logger.info("Buoy system initialized successfully")
        return True
    
    def create_status_packet(self, gps_data):
        return {
            'type': 'BUOY_STATUS',
            'buoy_id': BUOY_ID,
            'timestamp': datetime.now().isoformat(),
            'message_id': self.message_count,
            'gps': gps_data,
            'uptime': time.time(),
            'messages_relayed': self.message_count
        }
    
    def relay_vessel_message(self, vessel_data):
        gps_data = self.gps.read_position()
        
        relay_packet = {
            'type': 'RELAYED_MESSAGE',
            'buoy_id': BUOY_ID,
            'buoy_gps': gps_data,
            'timestamp': datetime.now().isoformat(),
            'message_id': self.message_count,
            'vessel_data': vessel_data
        }
        
        # Send to base station via LoRa
        success = self.lora.transmit_to_base(relay_packet)
        
        if success:
            self.message_count += 1
            logger.info(f"Relayed message from vessel (RSSI: {vessel_data.get('rssi', 'N/A')} dBm)")
            
            # Also send to cloud
            send_to_cloud('/api/buoy/data', relay_packet)
        
        return success
    
    def send_cloud_update(self):
        """Send status update to cloud"""
        gps_data = self.gps.read_position()
        status = self.create_status_packet(gps_data)
        
        success = send_to_cloud('/api/buoy/data', status)
        if success:
            logger.info("Cloud status update sent")
        
        return success
    
    def run(self):
        self.running = True
        last_status_time = time.time()
        status_interval = 60
        
        logger.info("Buoy system running...")
        logger.info("Listening for vessel messages...")
        
        try:
            while self.running:
                # Check for vessel messages
                vessel_message = self.lora.receive_from_vessel(timeout=0.1)
                if vessel_message:
                    logger.info(f"Received from vessel: {vessel_message.get('vessel_id', 'UNKNOWN')}")
                    self.relay_vessel_message(vessel_message)
                
                # Send periodic status to base
                current_time = time.time()
                if current_time - last_status_time >= status_interval:
                    gps_data = self.gps.read_position()
                    status = self.create_status_packet(gps_data)
                    self.lora.transmit_to_base(status)
                    self.message_count += 1
                    last_status_time = current_time
                
                # Send cloud updates
                if current_time - self.last_cloud_update >= CLOUD_UPDATE_INTERVAL:
                    self.send_cloud_update()
                    self.last_cloud_update = current_time
                
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        logger.info("Shutting down...")
        self.running = False
        self.lora.cleanup()
        self.gps.close()
        GPIO.cleanup()
        logger.info("Shutdown complete")

# ==================== MAIN ====================
if __name__ == "__main__":
    buoy = BuoySystem()
    
    if buoy.initialize():
        buoy.run()
    else:
        logger.error("Failed to initialize buoy system")
        exit(1)
