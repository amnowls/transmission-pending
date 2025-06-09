import machine
import network
import time
from machine import Pin, ADC, I2C, Timer
from lcd_api import LcdApi
from i2c_lcd import I2cLcd
from time import sleep
from umqtt.simple import MQTTClient

# WIFI and MQTT settings (unchanged)
WIFI_SSID = ":)" #my phone's hotspot
WIFI_PWD = "hellohello"
# WIFI_SSID = "UAL_IoT" #what we are using when doing UAL wifi
# WIFI_PWD = "TTrr3887@@SSTT"
MQTT_BROKER = "1083a817d2a54e99be1d22a06b29a5df.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "izanna"
MQTT_PASSWORD = "YayCCI101"
MQTT_TOPIC = "messages"
MQTT_CLIENT_ID = "Transmitter"
MQTT_STATUS_TOPIC = "status"

# Hardware setup (unchanged)
btn_select = Pin(15, Pin.IN, Pin.PULL_UP)
btn_space = Pin(16, Pin.IN, Pin.PULL_UP)
btn_delete = Pin(17, Pin.IN, Pin.PULL_UP)
btn_send = Pin(18, Pin.IN, Pin.PULL_UP)
potentiometer = ADC(Pin(34))
potentiometer.atten(ADC.ATTN_11DB)
potentiometer.width(ADC.WIDTH_12BIT)
#pad = ADC(Pin(35))
#pad.atten(ADC.ATTN_11DB)
#pad.width(ADC.WIDTH_12BIT)
led = Pin(2, Pin.OUT)

# LCD setup (unchanged)
I2C_ADDR = 0x27
totalRows = 4
totalColumns = 20
i2c = I2C(scl=Pin(22), sda=Pin(21), freq=10000)
lcd = I2cLcd(i2c, I2C_ADDR, totalRows, totalColumns)

# ===== NEW LETTER SELECTION SYSTEM =====
LETTER_ARRAY = "abcdefghijklmnopqrstuvwxyz.,!?"

# Weighted distribution (more resolution for common letters)
# Index weights: a(10), b(5), c(5)... z(2), .(3), ,(3), !(3), ?(3)
# LETTER_WEIGHTS = [
#     10, 5, 5, 5, 10, 5, 5, 5, 10, 2,  # a-j
#     2, 5, 5, 5, 10, 5, 2, 10, 10, 10,  # k-t
#     5, 2, 5, 2, 5, 2, 3, 3, 3, 3       # u-?
# ]
LETTER_WEIGHTS = [
    5, 5, 5, 5, 10, 5, 5, 5, 10, 2,  # a-j
    2, 5, 5, 5, 10, 5, 2, 10, 10, 10,  # k-t
    5, 2, 5, 2, 5, 2, 3, 3, 8, 3       # u-?
]

# Hysteresis control
last_pot_value = None
last_letter_index = None
HYSTERESIS_THRESHOLD = 50 
shutdown = False

def map_pot_to_letter(pot_value):
    """Non-linear mapping with weighted distribution"""
    total_weight = sum(LETTER_WEIGHTS)
    scaled = (pot_value / 4095) * total_weight
    cumulative = 0
    for i, weight in enumerate(LETTER_WEIGHTS):
        cumulative += weight
        if scaled <= cumulative:
            return i
    return len(LETTER_ARRAY) - 1

def get_stable_letter():
    """Get current letter with hysteresis filtering"""
    global last_pot_value, last_letter_index
    
    pot_value = potentiometer.read()
    
    # Initialises the pot
    if last_pot_value is None:
        last_pot_value = pot_value
        last_letter_index = map_pot_to_letter(pot_value)
        return LETTER_ARRAY[last_letter_index]
    
    # Only update if change exceeds threshold
    if abs(pot_value - last_pot_value) > HYSTERESIS_THRESHOLD:
        last_pot_value = pot_value
        last_letter_index = map_pot_to_letter(pot_value)
    
    return LETTER_ARRAY[last_letter_index]

def update_letter():
    global current_letter
    current_letter = get_stable_letter()  
    lcd.move_to(18, 0)
    lcd.putstr(current_letter)


# ----POTENTIOMETER ------
DEADZONE_BOTTOM = 0 #100    # given up on this idea but haven't changed code (will change to rotary encoder instead of pot)
DEADZONE_TOP = 4094 #3996      
ACTIVE_RANGE_MIN = DEADZONE_BOTTOM
ACTIVE_RANGE_MAX = DEADZONE_TOP
OUTPUT_MIN = 0
OUTPUT_MAX = 29
LETTER_ARRAY = "abcdefghijklmnopqrstuvwxyz.,!?"

led = Pin(2, Pin.OUT)
led.value(0)

mode = 1
change_mode = True
mode3_timer = 0
button_timer = 0

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
    
def check_network():
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print("WiFi disconnected, reconnecting...")
        connect_wifi()

def mqtt_callback(topic, msg):
    global shutdown, mode, change_mode
    print("Received message:", msg.decode())
    if "receiver: stepped on" in msg:
        led.on()
        print("LED turned ON")
    elif "receiver: stepped off" in msg:
        led.off()
        print("LED turned OFF")
    elif "shutdown" in msg:
        mode = 4
        change_mode = True
        shutdown = True
        
        
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


def map_with_deadzone(value):
    # kinda irrelevant at the moment
    if value <= DEADZONE_BOTTOM:
        return OUTPUT_MIN
    if value >= DEADZONE_TOP:
        return OUTPUT_MAX
    
    # Map the active range to output range
    active_range = DEADZONE_TOP - DEADZONE_BOTTOM
    scaled_value = value - DEADZONE_BOTTOM
    mapped_value = OUTPUT_MIN + (OUTPUT_MAX - OUTPUT_MIN) * (scaled_value / active_range)
    
    # Round to nearest integer (1-26)
    return round(mapped_value)


btn_select_pressed = False
btn_select_counter = 0
btn_select_waiting_release = False

btn_space_pressed = False
btn_space_counter = 0
btn_space_waiting_release = False

btn_delete_pressed = False
btn_delete_counter = 0
btn_delete_waiting_release = False

btn_send_pressed = False
btn_send_counter = 0
btn_send_waiting_release = False

message_update_counter = 0
update_letter_flag = False
current_letter = None

blink_update_counter = 0
blink_flag = False
blink_state_is_blank = True

message = ""
last_connection_check = 0
check_interval = 30  # seconds

person_on_pad = False
person_loaded = False


def update_letter():
     global lcd, current_letter, message
     value = potentiometer.read()
     char_value = map_with_deadzone(value)
     current_letter = LETTER_ARRAY[char_value]
     lcd.move_to(18, 0)
     lcd.putstr(current_letter)
     

def check_dial():
    global potentiometer, pot_value, last_pot_value, button_timer
    pot_value = potentiometer.read
    if last_pot_value == None:
        last_pot_value = potentiometer.read()
    pot_value = potentiometer.read()
    if  not(last_pot_value - 50 <= pot_value <= last_pot_value + 50):
        #button_timer = 20000
        return True


    pot_value = last_pot_value


def dial_timer():
    global potentiometer, pot_value, last_pot_value, button_timer
    pot_value = potentiometer.read()
    if last_pot_value is None:
        last_pot_value = pot_value
    # Only reset timer if change exceeds threshold
    if abs(pot_value - last_pot_value) > HYSTERESIS_THRESHOLD:
        button_timer = 20000
    last_pot_value = pot_value
    
    

def timer_callback(timer):
    global btn_select_waiting_release, btn_select_counter, btn_select_pressed, btn_select
    global btn_space_waiting_release, btn_space_counter, btn_space_pressed, btn_space
    global btn_delete_waiting_release, btn_delete_counter, btn_delete_pressed, btn_delete
    global btn_send_waiting_release, btn_send_counter, btn_send_pressed, btn_send
    global message_update_counter, update_letter_flag
    global blink_flag, blink_update_counter
    global mode3_timer, pad_timer
    global pad, person_on_pad, button_timer
    
    #select
    if btn_select_waiting_release:
        if btn_select.value() == 1:
            btn_select_waiting_release = False
            btn_select_counter = 0
    else:
        if btn_select.value() == 0:
            btn_select_counter += 1
            if btn_select_counter > 10:
                btn_select_pressed = True
                btn_select_waiting_release = True
                
    #space
    if btn_space_waiting_release:
        if btn_space.value() == 1:
            btn_space_waiting_release = False
            btn_space_counter = 0
    else:
        if btn_space.value() == 0:
            btn_space_counter += 1
            if btn_space_counter > 10:
                btn_space_pressed = True
                btn_space_waiting_release = True
    
    #delete
    if btn_delete_waiting_release:
        if btn_delete.value() == 1:
            btn_delete_waiting_release = False
            btn_delete_counter = 0
    else:
        if btn_delete.value() == 0:
            btn_delete_counter += 1
            if btn_delete_counter > 10:
                btn_delete_pressed = True
                btn_delete_waiting_release = True

    #send
    if btn_send_waiting_release:
        if btn_send.value() == 1:
            btn_send_waiting_release = False
            btn_send_counter = 0
    else:
        if btn_send.value() == 0:
            btn_send_counter += 1
            if btn_send_counter > 10:
                btn_send_pressed = True
                btn_send_waiting_release = True
                
                
    if not update_letter_flag:
        message_update_counter += 1
        if message_update_counter >= 100:
            message_update_counter = 0
            update_letter_flag = True
            
    if not blink_flag:
        blink_update_counter += 1
        if blink_update_counter >500:
            blink_update_counter = 0
            blink_flag = True
            
    if mode3_timer > 0:
        mode3_timer = mode3_timer - 1
    
    if button_timer > 0:
        button_timer = button_timer - 1
        
        
    

def display_message():
    global lcd, message
    lcd.move_to(0, 1)
    lcd.putstr(message)
    
    
def do_select():
    global current_letter, message, button_timer
    if len(message) < 60:
        message += current_letter
        display_message()
        button_timer = 20000
        
    

def do_space():
    global message, button_timer
    if len(message) < 60:
        message += "_"
        display_message()
        button_timer = 20000
    
def do_delete():
    global message
    if len(message) > 0:
        message = message[:-1]
        message_length = len(message)
        #lcd.move_to(message_length % 20, 1+int(message_length//20))
        #lcd.putstr(" "+" " if message_length < 59 else "") #Double space to delete blinking character
        lcd.move_to(message_length % 20, 1+int(message_length/20))
        lcd.putstr(" "+" " if message_length < 59 else "")
        button_timer = 20000
        
def do_send():
    global message, mqtt_client, message_array
    for x in message:
        if x == "_":
            message = message.replace(x, " ")
    print(message)
    #message = message_array.decode('utf-8')
    #print(message)
    mqtt_client.publish(MQTT_TOPIC, message.encode('utf-8'))
    do_stepped_off()


def do_stepped_on():
    global mqtt_client
    mqtt_client.publish(MQTT_STATUS_TOPIC, "transmitter: stepped on")
    
def do_stepped_off():
    global mqtt_client
    mqtt_client.publish(MQTT_STATUS_TOPIC, "transmitter: stepped off")

def do_mode2():
    global mode, change_mode
    mode = 2
    change_mode = True
    do_stepped_on()
    

    

        
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
mqtt_client.publish(MQTT_STATUS_TOPIC, "transmitter: online")
#mqtt_client.publish(MQTT_STATUS_TOPIC, "", retain=True)

# Initialize your variables 
last_connection_check = 0
check_interval = 30  # seconds







periodic_timer = Timer(0)
periodic_timer.init(period=1, mode=Timer.PERIODIC, callback=timer_callback)
led.on()


while True:
    
    mqtt_client.check_msg()
    # Check connection only every 30 seconds
    current_time = time.time()
        
    if current_time - last_connection_check >= check_interval:
        check_network()
        check_connection()
        last_connection_check = current_time
    
            

    if mode == 1:
        if change_mode:
            button_timer = 20000
            lcd.clear()
            lcd.move_to(3,1)
            lcd.putstr("turn the dial")
            lcd.move_to(5,2)
            lcd.putstr("to begin!")
            btn_select_pressed = False
            btn_space_pressed = False
            btn_delete_pressed = False
            btn_send_pressed = False
            change_mode = False
            last_pot_value = potentiometer.read()

        if btn_select_pressed:
            print("SELECT BUTTON PRESSED")
            do_mode2()
            btn_select_pressed = False
        
        if btn_space_pressed:
            print("SPACE BUTTON PRESSED")
            do_mode2()
            btn_space_pressed = False
        
        if btn_delete_pressed:
            print("DELETE BUTTON PRESSED")
            do_mode2()
            btn_delete_pressed = False

        if btn_send_pressed:
            print("SEND BUTTON PRESSED")
            do_mode2()
            btn_send_pressed = False

        
        if update_letter_flag:
            if check_dial():
                do_mode2()
            update_letter_flag = False
                

        

    if mode == 2:
        
        if change_mode:
            lcd.clear()
            message = ""
            btn_select_pressed = False
            btn_space_pressed = False
            btn_delete_pressed = False
            btn_send_pressed = False
            #lcd.move_to(0,0)
            #lcd.putstr("COMPOSE")
            lcd.move_to(11, 0)
            lcd.putstr("input:")
            #lcd.move_to(0,1)
            #lcd.putstr("--------------------")
            #lcd.move_to(0,3)
            #lcd.putstr("--------------------")
            change_mode = False

        if btn_select_pressed:
            print("SELECT BUTTON PRESSED")
            do_select()
            btn_select_pressed = False
        
        if btn_space_pressed:
            print("SPACE BUTTON PRESSED")
            do_space()
            btn_space_pressed = False
        
        if btn_delete_pressed:
            print("DELETE BUTTON PRESSED")
            do_delete()
            btn_delete_pressed = False

        if btn_send_pressed:
            print("SEND BUTTON PRESSED")
            do_send()
            btn_send_pressed = False
            mode = 3
            change_mode = True
        
        if update_letter_flag:
            update_letter()
            dial_timer()
            update_letter_flag = False
    
        if blink_flag:
            blink_flag = False
            blink_state_is_blank = not blink_state_is_blank
            message_length = len(message)
            #if message_length < 60:
                #lcd.move_to(1+(message_length % 20), 1+int(message_length // 20))
                #lcd.putstr(current_letter if blink_state_is_blank else " ")
            if message_length < 60:
                lcd.move_to(message_length % 20, 1+int(message_length/20))
                lcd.putstr(current_letter if blink_state_is_blank else " ")
        print(button_timer)        
        if button_timer == 0:
            mode = 1
            change_mode = True
            do_stepped_off()
                
    if mode == 3:
         if change_mode:
             lcd.clear()
             lcd.move_to(5,1)
             lcd.putstr("message sent")
             lcd.move_to(7,2)
             lcd.putstr("thank you")
             message = ""
             mode3_timer = 10000
             change_mode = False
         if mode3_timer == 0:
             mode = 1
             change_mode = True
    
    #sleep mode when it all goes a bit wrong
    if mode == 4:
        if change_mode:
            lcd.clear()
            lcd.move_to(6,1)
            lcd.putstr("ZzzZzzZz")
            change_mode = False
            
         
