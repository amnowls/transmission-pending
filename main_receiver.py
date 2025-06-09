import machine
import network
import time
from machine import Pin, ADC, I2C, Timer, DAC
from lcd_api import LcdApi
from i2c_lcd import I2cLcd
from time import sleep
from umqtt.simple import MQTTClient
import urequests
import utime


#WIFI_SSID = "The Burrow"
#WIFI_PWD = "a2b2c3d2e2"
WIFI_SSID = ":)"
WIFI_PWD = "hellohello"
# WIFI_SSID = "UAL_IoT"
# WIFI_PWD = "TTrr3887@@SSTT"
# WIFI_SSID = "bowl (3)"
# WIFI_PWD = "poo33311"
# WIFI_SSID = "UAL_IoT"
# WIFI_PWD = "TTrr3887@@SSTT"


VOICERSS_API_KEY = 'b48695a97da04a39b64e5a5678bb89b9'
TTS_URL = 'https://api.voicerss.org/'

dac = DAC(Pin(25))  # DAC output on GPIO 26


# MQTT settings
MQTT_BROKER = "1083a817d2a54e99be1d22a06b29a5df.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "izanna"
MQTT_PASSWORD = "YayCCI101"
MQTT_TOPIC = "messages"
MQTT_CLIENT_ID = "Receiver"  # Should be unique per device
MQTT_STATUS_TOPIC = "status"


# pad = ADC(Pin(35))
# pad.atten(ADC.ATTN_11DB)  # Full range 0-3.3V
# pad.width(ADC.WIDTH_12BIT)  # 0-4095 range
led = Pin(2, Pin.OUT)


I2C_ADDR = 0x27
totalRows = 4
totalColumns = 20

i2c = I2C(scl=Pin(22), sda=Pin(21), freq=10000)       #initializing the I2C method for ESP8266
lcd = I2cLcd(i2c, I2C_ADDR, totalRows, totalColumns)


led = Pin(2, Pin.OUT)
led.value(0)

mode = 2
change_mode = True
mode2_timer = 0
mode4_timer = 0
mode5_timer = 0
mode6_timer = 0
mode7_timer = 0
# pad_timer = 0
response = ""

message_array=[]
newmessage = ""
# person_on_pad = False
# person_loaded = False


def connect_wifi(debug=False):
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print("Connecting to WiFi...")
        if debug:
            lcd.move_to(0,0)
            lcd.putstr("Connecting to Wifi..")
        sta_if.active(True)
        sta_if.connect(WIFI_SSID, WIFI_PWD)
        while not sta_if.isconnected():
            time.sleep(0.5)
    print("WiFi connected:", sta_if.ifconfig())
    led.on()

    
def check_network():
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print("WiFi disconnected, reconnecting...")
        connect_wifi()
        

def mqtt_callback(topic, msg):
    global message, change_mode, mode
    print("Received message:", msg.decode())
    if topic == b"status":
        if "transmitter: stepped on" in msg:
            led.on()
            print("LED turned ON")
        elif "transmitter: stepped off" in msg:
#             led.off()
            print("LED turned OFF")
        elif "shutdown" in msg:
            mode = 6
            change_mode = True
        
    if topic == b"messages":
        if msg != b"":
            #print("Received message:", msg.decode())
            message = msg.decode('utf-8')
            #message = msg
            mode = 4
            change_mode = True
        
def connect_mqtt():
    while True:
        try:
            mqtt_client = MQTTClient(client_id=MQTT_CLIENT_ID, server=MQTT_BROKER, port=MQTT_PORT, 
                                     user=MQTT_USER, password=MQTT_PASSWORD, ssl=True, 
                                     ssl_params={'server_hostname': MQTT_BROKER})
            mqtt_client.connect()
            print("Connected to MQTT broker")
            
            mqtt_client.set_last_will(
                topic=MQTT_STATUS_TOPIC,
                msg="offline",
                retain=True,
                qos=1
            )

            mqtt_client.set_callback(mqtt_callback)
            mqtt_client.subscribe(MQTT_TOPIC)
            print(f"Subscribed to topic: {MQTT_TOPIC}")
            mqtt_client.subscribe(MQTT_STATUS_TOPIC)
            print(f"Subscribed to topic: {MQTT_STATUS_TOPIC}")
            return mqtt_client
        except Exception as e:
            print(f"Connection failed: {e}")
            time.sleep(5)


message = ""
last_connection_check = 0
check_interval = 30  # seconds
    

def timer_callback(timer):
    global mode2_timer, mode4_timer, mode5_timer, mode6_timer
            
    if mode2_timer > 0:
        mode2_timer = mode2_timer - 1
        
    if mode4_timer > 0:
        mode4_timer = mode4_timer - 1
    
    if mode5_timer > 0:
        mode5_timer = mode5_timer - 1
        
    if mode6_timer > 0:
        mode6_timer = mode6_timer - 1
        
#     if mode7_timer > 0:
#         mode7_timer = mode7_timer -1
        
#     if pad_timer > 0:
#         pad_timer = pad_timer - 1
#         
#     
#     pad_level = pad.read()
#     #print(pad_level)
#     if pad_level > 1000:
#         person_on_pad = True
#     elif pad_level < 500:
#         person_on_pad = False
    

def play_streaming_audio(text, sample_rate=8000):
    global response
    """
    Stream audio from TTS service and play directly through DAC
    without storing the entire file in memory.
    """
    print(f"Requesting TTS for: '{text[:20]}...'")  # Show first 20 chars of text
    print(f"Full URL: {TTS_URL}?key=...&hl=en-us&src={text[:10]}...")
    params = {
        "key": VOICERSS_API_KEY,
        "hl": "en-us",
        "src": text,
        "c": "WAV",
        "f": "8khz_8bit_mono"  # Using 8kHz 8-bit mono to minimize data
    }
    
    # Build query string
    query = '&'.join(['{}={}'.format(k, v.replace(' ', '+')) for k, v in params.items()])
    full_url = TTS_URL + "?" + query
    
    # Calculate delay between samples for correct playback speed
    delay_us = int(1_000_000 / sample_rate)
    
    try:
        # Make streaming HTTP request
        response = urequests.get(full_url, stream=True)
        if response.status_code == 200:
            print("Beginning audio stream...")
            mode = 4
            
            # Skip WAV header (first 44 bytes)
            wav_header = response.raw.read(44)
            if len(wav_header) != 44:
                print("Invalid WAV header")
                return False
                
            # Stream and play audio in chunks
            chunk_size = 512  # Adjust based on your memory constraints
            while True:
                chunk = response.raw.read(chunk_size)
                if not chunk:
                    break  # End of stream
                
                # Process each byte in the chunk
                for byte in chunk:
                    dac.write(byte)
                    utime.sleep_us(delay_us)
            
            print("Playback complete")
            return True
            
        else:
            print(f"TTS request failed with status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error during streaming playback: {e}")
        return False
        
    finally:
        # Ensure response is closed
        try:
            response.close()
        except:
            pass
        gc.collect()

# ===== PLAY AUDIO VIA DAC =====
def play_audio_pcm(audio_data, sample_rate=8000):
    delay_us = int(1_000_000 / sample_rate)

    print("Playing audio...")
    for byte in audio_data:
        dac.write(byte)
        utime.sleep_us(delay_us)
    print("Playback finished.")
    

def play_saved_audio(text, sample_rate=8000):
    """
    Request TTS audio once, save to file, then play from file.
    """
    global response
    filename = "tts_audio.wav"
    
    print(f"Requesting TTS for: '{text[:20]}...'")  # Show first 20 chars of text
    print(f"Full URL: {TTS_URL}?key=...&hl=en-us&src={text[:10]}...")
    params = {
        "key": VOICERSS_API_KEY,
        "hl": "en-us",
        "src": text,
        "c": "WAV",
        "f": "8khz_8bit_mono"  # Using 8kHz 8-bit mono to minimize data
    }
    
    # Build query string
    query = '&'.join(['{}={}'.format(k, v.replace(' ', '+')) for k, v in params.items()])
    full_url = TTS_URL + "?" + query
    
    try:
        # Make HTTP request and save to file
        print("Downloading audio file...")
        response = urequests.get(full_url)
        if response.status_code == 200:
            # Save the entire response to a file
            with open(filename, "wb") as f:
                f.write(response.content)
            print("Audio file saved successfully")
            
            # Now play from the saved file
            return play_from_file(filename, sample_rate)
        else:
            print(f"TTS request failed with status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error during audio download: {e}")
        return False
        
    finally:
        # Ensure response is closed
        try:
            response.close()
        except:
            pass
        gc.collect()

def play_from_file(filename, sample_rate=8000):
    """
    Play audio from a saved WAV file through DAC
    """
    # Calculate delay between samples for correct playback speed
    delay_us = int(1_000_000 / sample_rate)
    
    try:
        print(f"Playing audio from file: {filename}")
        with open(filename, "rb") as f:
            # Skip WAV header (first 44 bytes)
            wav_header = f.read(44)
            if len(wav_header) != 44:
                print("Invalid WAV header")
                return False
                
            # Read and play audio in chunks
            chunk_size = 512  # Adjust based on your memory constraints
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break  # End of file
                
                # Process each byte in the chunk
                for byte in chunk:
                    dac.write(byte)
                    utime.sleep_us(delay_us)
            
            print("Playback complete")
            return True
            
    except Exception as e:
        print(f"Error during file playback: {e}")
        return False
    finally:
        gc.collect()




def speak(text):
    check_network()
    print(f"Attempting to speak: '{text}'")
    gc.collect()
    try:
        success = play_streaming_audio(text)
        print(f"Audio playback {'succeeded' if success else 'failed'}")
    except Exception as e:
        print(f"Speak error: {e}")
    gc.collect()
        
# Main execution starts here
lcd.clear()
connect_wifi(True)
check_network()  # Connect to WiFi first

# Now connect to MQTT and get the client object
mqtt_client = connect_mqtt()

def check_connection():
    global mqtt_client
    try:
        mqtt_client.ping()
    except:
        print("Connection lost, reconnecting...")
        try:
            mqtt_client.disconnect()
        except:
            pass
        mqtt_client = connect_mqtt()

# Publish online status
mqtt_client.publish(MQTT_STATUS_TOPIC, "receiver: online")
#mqtt_client.publish(MQTT_STATUS_TOPIC, "", retain=True)

# Initialize your variables 
last_connection_check = 0
check_interval = 30  # seconds


periodic_timer = Timer(0)
periodic_timer.init(period=1, mode=Timer.PERIODIC, callback=timer_callback)

# def do_pad_loaded():
#     global mqtt_client
#     mqtt_client.publish(MQTT_STATUS_TOPIC, "receiver: stepped on")
#     
# def do_pad_unloaded():
#     global mqtt_client
#     mqtt_client.publish(MQTT_STATUS_TOPIC, "receiver: stepped off")

while True:
    
    mqtt_client.check_msg()
    current_time = time.time()
    if current_time - last_connection_check >= check_interval:
        check_network()
        check_connection()
        last_connection_check = current_time
        
#     
#     if not person_loaded and person_on_pad : # new person on pad!
#         person_loaded = True
#         do_pad_loaded()
#         if mode == 1:
#             mode = 2
#             change_mode = True
#             
#     if person_loaded and not person_on_pad: # person stepped off!
#         person_loaded = False
#         do_pad_unloaded()
#         if mode == 2:
#             pad_timer = 10000
#             
#     if mode == 2:
#         if pad_timer == 0 and not person_on_pad:
#             mode = 1
#             change_mode = True
#     
# 
#                  
#     if mode == 1:
#         if change_mode:
#             lcd.clear()
#             lcd.move_to(1,1)
#             lcd.putstr("pick up speaker")
#             lcd.move_to(5,2)
#             lcd.putstr("to begin!")
#             change_mode = False
#             person_loaded = False
# 
# 
#         

    if mode == 2:
        if change_mode:
            lcd.clear()
            if message == "":
                lcd.move_to(4,1)
                lcd.putstr("get ready to")
                lcd.move_to(1,2)
                lcd.putstr("receive a message")
            else:
                lcd.move_to(5,1)
                lcd.putstr("get ready!")
                lcd.move_to(0,2)
                lcd.putstr("playing last message")
            change_mode = False
            mode2_timer = 0  # start countdown

        if message != "":  # Only play audio if there's something to say
            if mode2_timer == 0:
                speak("last sent message")
                mode2_timer = 400
                speak(message)
                mode2_timer = 1000  # adjust delay before repeating


            
    if mode == 3:
         if change_mode:
             lcd.clear()
             lcd.move_to(1,1)
             lcd.putstr("someone is writing")
             lcd.move_to(3,2)
             lcd.putstr("you a message...")
             change_mode = False
         if mode3_timer == 0:
#              mode = 1
             mode = 2

             change_mode = True
    
    if mode == 4:
        if change_mode:
            lcd.clear()
            lcd.move_to(2,0)
            lcd.putstr("message inbound!")
            lcd.move_to(2,1)
            lcd.putstr("listen carefully")
            lcd.move_to(2,3)
            lcd.putstr("plays once only!")
            change_mode = False
            speak(message)
            mode4_timer = 1000  # Delay before playing audio
        if mode4_timer == 0:
            print(f"\n=== ATTEMPTING TO SPEAK ===\nMessage: '{message}'\n")
            #speak(message)  # Play audio HERE
            mode = 5
            change_mode = True
            
    
    if mode == 5:
        if change_mode:
            lcd.clear()
            lcd.move_to(5,1)
            lcd.putstr("thank you")
            lcd.move_to(3,2)
            lcd.putstr("for listening.")
            change_mode = False
            mode5_timer = 6000
        if mode5_timer == 0:
#             mode = 1
            mode = 2

            change_mode = True   
            
            
    if mode == 6:
        if change_mode:
            lcd.clear()
            lcd.move_to(6,1)
            lcd.putstr("ZzzZzzZz")
            #speak("I'm trying to sleep, please put me down, zzzzzzzzzzzzzzzzzzzzzzz")
            play_saved_audio("Im sleeping zzzz")
            change_mode = False
        
        if mode6_timer == 0:
            #play_audio_pcm(response)
            play_from_file("tts_audio.wav")
            mode6_timer = 1000
            
        

                
                    
#     if mode == 7
#         if change_mode:
#             lcd.clear()
#             lcd.move_to(1,1)
#             lcd.putstr("playing last sent")
#             lcd.move_to(2,4)
#             lcd.putstr("message.")
#             change_mode = False
#             mode7_timer = 1000
# 
#             speak(message)
# 
#             
#          
    
            
        
    






