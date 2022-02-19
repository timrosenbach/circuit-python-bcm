import adafruit_gps
import adafruit_displayio_ssd1305
from adafruit_display_text import label
import asyncio
import board
import busio
import displayio
import keypad
import math
import microcontroller
import rtc
import terminalio
import time

class Control:
    def __init__(self, gps, display):
        self.gps = gps
        self.display = display
        self.rtc = rtc.RTC()
        self.mode = 0
        self.distance = 0
        self.latitude = 0
        self.longitude = 0

def initGPS():
    TX = board.GP0
    RX = board.GP1
    uart = busio.UART(TX, RX, baudrate = 9600, timeout = 10)
    gps = adafruit_gps.GPS(uart, debug = False)
    gps.send_command(b"PMTK251,9600")
    gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
    gps.send_command(b"PMTK220,1000")
    gps.send_command(b"PMTK255,1")
    
    rtc.set_time_source(gps)
    
    return gps

def initDisplay(width = 128, height = 32):
    BORDER = 8
    FONTSCALE = 1

    CLK = board.GP10
    MOSI = board.GP11
    DC = board.GP8
    CS = board.GP9
    RST = board.GP12
    
    spi = busio.SPI(clock = CLK, MOSI = MOSI)
    display_bus = displayio.FourWire(spi, command = DC, chip_select = CS, baudrate = 1000000, reset = RST)

    return adafruit_displayio_ssd1305.SSD1305(display_bus, width = width, height = height)

def _format_datetime(datetime):
    return "{:02}:{:02}:{:02}".format(
        datetime.tm_hour,
        datetime.tm_min,
        datetime.tm_sec,
    )

def _convertKnotsToKmh(knots):
    if knots == None:
        return 0
    
    return math.floor(knots * 1.852)

def displayConnecting(control):
    text = "Connecting"
    text_area = label.Label(terminalio.FONT, text = text, scale = 1)
    text_area.anchor_point = (0.5, 0.5)
    text_area.anchored_position = (128 / 2, 32 / 2)
    control.display.show(text_area)

def displayTime(control):
    text = _format_datetime(control.rtc.datetime)

    text_area = label.Label(terminalio.FONT, text = text, scale = 2)
    text_area.anchor_point = (0.5, 0.5)
    text_area.anchored_position = (128 / 2, 32 / 2)
    control.display.show(text_area)
    
def displaySpeed(control):
    text = "{} km/h".format(_convertKnotsToKmh(control.gps.speed_knots))

    text_area = label.Label(terminalio.FONT, text = text, scale = 2)
    text_area.anchor_point = (0.5, 0.5)
    text_area.anchored_position = (128 / 2, 32 / 2)
    control.display.show(text_area)
    
def displayHeading(control):
    text = "{}'".format(control.gps.track_angle_deg)
    
    text_area = label.Label(terminalio.FONT, text = text, scale = 2)
    text_area.anchor_point = (0.5, 0.5)
    text_area.anchored_position = (128 / 2, 32 / 2)
    control.display.show(text_area)

def displayDistance(control):
    text = "{} m".format(math.floor(control.distance))

    text_area = label.Label(terminalio.FONT, text = text, scale = 2)
    text_area.anchor_point = (0.5, 0.5)
    text_area.anchored_position = (128 / 2, 32 / 2)
    control.display.show(text_area)
    
def displaySatellites(control):
    text = "{} Satelliten".format(control.gps.satellites)
    
    text_area = label.Label(terminalio.FONT, text = text, scale = 1)
    text_area.anchor_point = (0.5, 0.5)
    text_area.anchored_position = (128 / 2, 32 / 2)
    control.display.show(text_area)

def displayTemperature(control):
    text = "{} Grad".format(math.floor(microcontroller.cpu.temperature))

    text_area = label.Label(terminalio.FONT, text = text, scale = 2)
    text_area.anchor_point = (0.5, 0.5)
    text_area.anchored_position = (128 / 2, 32 / 2)
    control.display.show(text_area)
    
async def updateGPS(control):
    while True:
        control.gps.update()
        await asyncio.sleep(1)
        
async def refreshDisplay(control):
    while True:
        if not control.gps.has_fix:        
            displayConnecting(control)
        else:
            if control.mode == 0:
                displaySpeed(control)
            elif control.mode == 1:
                displayHeading(control)
            elif control.mode == 2:
                displayDistance(control)
            elif control.mode == 3:
                displayTime(control)
            elif control.mode == 4:
                displaySatellites(control)
            elif control.mode == 5:
                displayTemperature(control)
                
        await asyncio.sleep(1)
        
async def calculateDistance(control):
    while True:
        if control.gps.has_fix:
            latitude = control.gps.latitude
            longitude = control.gps.longitude
            
            if (control.latitude == 0 and control.longitude == 0):
                control.latitude = latitude
                control.longitude = longitude
                continue
            
            print("\n")
            print("Aktuelle Latitude: {}".format(latitude))
            print("Aktuelle Longitude: {}".format(longitude))
            print("Letzte Latitude: {}".format(control.latitude))
            print("Letzte Longitude: {}".format(control.longitude))            
                
            R = 6371e3
            φ1 = control.latitude * math.pi / 180
            φ2 = latitude * math.pi / 180
            
            Δφ = (latitude - control.latitude) * math.pi / 180
            Δλ = (longitude - control.longitude) * math.pi / 180
            
            a = math.sin(Δφ / 2) * math.sin(Δφ / 2) + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) * math.sin(Δλ / 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            
            d = R *  c
            
            control.latitude = latitude
            control.longitude = longitude
            control.distance += d
            
            print("Distanz: {}".format(d))
        
        await asyncio.sleep(1)
        
async def catch_pin_transitions(control, pin):
    with keypad.Keys((pin,), value_when_pressed=False) as keys:
        while True:
            event = keys.events.get()
            if event:
                if event.pressed:
                    if control.mode < 5:
                        control.mode += 1
                    else:
                        control.mode = 0
                    print("Current mode: {}".format(control.mode))
                elif event.released:
                    print("pin went high")
                    
            await asyncio.sleep(0)

# Release any previously configured displays
displayio.release_displays()

async def main():    
    control = Control(initGPS(), initDisplay())
    gps_task = asyncio.create_task(updateGPS(control))
    display_task = asyncio.create_task(refreshDisplay(control))
    distance_task = asyncio.create_task(calculateDistance(control))
    button_interrupt_task = asyncio.create_task(catch_pin_transitions(control, board.GP16))
    
    # This will run forever, because no tasks ever finish.
    await asyncio.gather(gps_task, display_task, distance_task, button_interrupt_task)


asyncio.run(main())