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

WIDTH = 128
HEIGHT = 32
DEBUG = False

class Mode:
    def __init__(self, control, active):
        self.active = active
        self.control = control
        
    def render(self):
        raise NotImplementedError('Subclasses must override render()!')

class Connecting(Mode):
    def render(self):
        text = "BOOTing..."
        text_area = label.Label(terminalio.FONT, text = text, scale = 1)
        text_area.anchor_point = (0.5, 0.5)
        text_area.anchored_position = (WIDTH / 2, HEIGHT / 2)
        self.control.display.show(text_area)
    
class Speed(Mode):
    def render(self):
        text = "{} km/h".format(_convertKnotsToKmh(self.control.gps.speed_knots))
        text_area = label.Label(terminalio.FONT, text = text, scale = 2)
        text_area.anchor_point = (0.5, 0.5)
        text_area.anchored_position = (WIDTH / 2, HEIGHT / 2)
        self.control.display.show(text_area)
        
class Distance(Mode):
    def render(self):
        distance = self.control.distance
        
        text = None
        if distance < 1000:
            text = "{} m".format(round(distance))
        else:
            text = "{} km".format(round(distance / 1000, 2))
            
        text_area = label.Label(terminalio.FONT, text = text, scale = 2)
        text_area.anchor_point = (0.5, 0.5)
        text_area.anchored_position = (WIDTH / 2, HEIGHT / 2)
        self.control.display.show(text_area)
        
class Heading(Mode):
    def render(self):
        text = "{}'".format(self.control.gps.track_angle_deg)    
        text_area = label.Label(terminalio.FONT, text = text, scale = 2)
        text_area.anchor_point = (0.5, 0.5)
        text_area.anchored_position = (WIDTH / 2, HEIGHT / 2)
        self.control.display.show(text_area)
        
class Time(Mode):
    def render(self):
        text = "{} Uhr".format(_format_datetime(time.localtime()))
        text_area = label.Label(terminalio.FONT, text = text, scale = 2)
        text_area.anchor_point = (0.5, 0.5)
        text_area.anchored_position = (WIDTH / 2, HEIGHT / 2)
        self.control.display.show(text_area)
        
class Satellites(Mode):
    def render(self):
        text = "{} Satelliten".format(self.control.gps.satellites)    
        text_area = label.Label(terminalio.FONT, text = text, scale = 1)
        text_area.anchor_point = (0.5, 0.5)
        text_area.anchored_position = (WIDTH / 2, HEIGHT / 2)
        self.control.display.show(text_area)
        
class Temperature(Mode):
    def render(self):
        text = "{} Grad".format(round(microcontroller.cpu.temperature, 1))
        text_area = label.Label(terminalio.FONT, text = text, scale = 2)
        text_area.anchor_point = (0.5, 0.5)
        text_area.anchored_position = (WIDTH / 2, HEIGHT / 2)
        self.control.display.show(text_area)
        
class Control:
    def __init__(self, gps, display):
        self.gps = gps      
        self.display = display
        self.modes = [Speed(self, True), Distance(self, False), Heading(self, False), Time(self, False), Temperature(self, False), Satellites(self, False)]
        self.buttonPressedAt = 0
        self.distance = 0
        self.latitude = 0
        self.longitude = 0

def initGPS():
    TX = board.GP0
    RX = board.GP1
    uart = busio.UART(TX, RX, baudrate = 9600, timeout = 10)
    gps = adafruit_gps.GPS(uart, debug = DEBUG)
    
    gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
    gps.send_command(b"PMTK220,1000")
    
    return gps

def initDisplay(width = WIDTH, height = HEIGHT):
    CLK = board.GP10
    MOSI = board.GP11
    DC = board.GP8
    CS = board.GP9
    RST = board.GP12
    
    spi = busio.SPI(clock = CLK, MOSI = MOSI)
    display_bus = displayio.FourWire(spi, command = DC, chip_select = CS, baudrate = 1000000, reset = RST)
    
    return adafruit_displayio_ssd1305.SSD1305(display_bus, width = width, height = height)

def _format_datetime(datetime):
    UTC_OFFSET = 1
    hour = datetime.tm_hour + UTC_OFFSET if datetime.tm_hour < 23 else 0
    return "{:02}:{:02}".format(
        hour,
        datetime.tm_min,
    )

def _convertKnotsToKmh(knots):
    if knots == None:
        return 0
    
    return round(knots * 1.852)
    
def getActiveMode(control):
    for index, mode in enumerate(control.modes):
        if mode.active:
            return index, mode
        
def switchMode(control):
    activeMode = getActiveMode(control)
    activeMode[1].active = False
    if activeMode[0] < len(control.modes) - 1:
        control.modes[activeMode[0] + 1].active = True
    else:
        control.modes[0].active = True
        
    if DEBUG:
        print("\n")
        print("Switching mode to {}".format(type(getActiveMode(control)[1]).__name__))
    
async def updateGPS(control):
    while True:
        control.gps.update()
        await asyncio.sleep(0)
        
async def refreshDisplay(control):
    while True:
        if not control.gps.has_fix:
            Connecting(control, True).render()
        else:        
            getActiveMode(control)[1].render()       
        
        await asyncio.sleep(0.5)
        
async def calculateDistance(control):
    while True:
        if control.gps.has_fix:
            start = time.monotonic()
            
            latitude = control.gps.latitude
            longitude = control.gps.longitude
            
            if (control.latitude == 0 and control.longitude == 0):
                control.latitude = latitude
                control.longitude = longitude
                continue
                
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
            
            end = time.monotonic()
            
            duration = end - start
            
            if DEBUG:
                print("\n")
                print("Aktuelle Latitude: {}".format(latitude))
                print("Aktuelle Longitude: {}".format(longitude))
                print("Letzte Latitude: {}".format(control.latitude))
                print("Letzte Longitude: {}".format(control.longitude)) 
                print("Distanz: {}".format(d))
                print("Dauer: {}".format(duration))
        
        await asyncio.sleep(2)
        
async def catch_pin_transitions(control, pin):
    with keypad.Keys((pin,), value_when_pressed=False) as keys:
        while True:
            event = keys.events.get()
            if event:
                if event.pressed:
                    control.buttonPressedAt = time.monotonic()
                elif event.released:
                    releasedAt = time.monotonic()
                    
                    longPressed = False
                    duration = releasedAt - control.buttonPressedAt
                    
                    a_type = type(getActiveMode(control)[1])                    
                    if a_type.__name__ == "Distance" and duration >= 5:
                        control.distance = 0
                        control.buttonPressedAt = 0
                        longPressed = True
                        
                        if DEBUG:
                            print("\n")
                            print("long press")
                        
                    if not longPressed:
                        switchMode(control)
                    
            await asyncio.sleep(0)

async def main():
    control = Control(initGPS(), initDisplay())
    gps_task = asyncio.create_task(updateGPS(control))
    display_task = asyncio.create_task(refreshDisplay(control))
    distance_task = asyncio.create_task(calculateDistance(control))
    button_interrupt_task = asyncio.create_task(catch_pin_transitions(control, board.GP15))
    
    # This will run forever, because no tasks ever finish.
    await asyncio.gather(gps_task, display_task, distance_task, button_interrupt_task)


# Release any previously configured displays
displayio.release_displays()

asyncio.run(main())