from ast import match_case
from asyncio import TimerHandle
import json
from time import sleep
from turtle import home
from onvif import ONVIFCamera
import sys, os
sys.stdout = open(os.devnull, 'w')
import pygame
sys.stdout = sys.__stdout__

DEV = True

dead_zone = 0.09
last_button_pressed = "None"
flip = False
slow = False

axis_left_pan = 0.000
axis_left_tilt = 0.000
axis_right_pan = 0.000
axis_right_tilt = 0.000

active_cam = None
cam1 = None
cam2 = None
cam3 = None
cam4 = None

cam1Active = False
cam2Active = False

is_running = False
controller = None

#debouncers
stop_called = False
home_called = False
flip_called = False
slow_called = False

basedir = './' if DEV else  os.path.dirname(sys.executable) 

class PtzControl(object):
    def __init__(self, ip,  port, user, password):
        super(PtzControl, self,).__init__()
        self.mycam = ONVIFCamera(ip, port, user, password, wsdl_dir=os.path.join(basedir, 'wsdl'))
        # create media service object
        self.media = self.mycam.create_media_service()
        # Get target profile
        self.media_profile = self.media.GetProfiles()[0]
        # Use the first profile and Profiles have at least one
        token = self.media_profile.token
        # PTZ controls  -------------------------------------------------------------
        self.ptz = self.mycam.create_ptz_service()
        # Get available PTZ services
        request = self.ptz.create_type('GetServiceCapabilities')
        Service_Capabilities = self.ptz.GetServiceCapabilities(request)

        # IMG controls  -------------------------------------------------------------
        self.img = self.mycam.create_imaging_service()
        print(self.img.Capabilities())

        # Get PTZ status
        status = self.ptz.GetStatus({'ProfileToken': token})
        # print("STATUS: ", status.Position)

        # Get PTZ configuration options for getting option ranges
        request = self.ptz.create_type('GetConfigurationOptions')
        request.ConfigurationToken = self.media_profile.PTZConfiguration.token
        ptz_configuration_options = self.ptz.GetConfigurationOptions(request)

        # get continuousMove request -- requestc
        self.requestc = self.ptz.create_type('ContinuousMove')
        self.requestc.ProfileToken = self.media_profile.token
        if self.requestc.Velocity is None:
            self.requestc.Velocity = self.ptz.GetStatus(
                {'ProfileToken': self.media_profile.token}).Position
            self.requestc.Velocity.PanTilt.space = ptz_configuration_options.Spaces.ContinuousPanTiltVelocitySpace[
                0].URI
            self.requestc.Velocity.Zoom.space = ptz_configuration_options.Spaces.ContinuousZoomVelocitySpace[
                0].URI

        self.requests = self.ptz.create_type('Stop')
        self.requests.ProfileToken = self.media_profile.token
        self.requestp = self.ptz.create_type('SetPreset')
        self.requestp.ProfileToken = self.media_profile.token
        self.requestg = self.ptz.create_type('GotoPreset')
        self.requestg.ProfileToken = self.media_profile.token
        self.requestHome = self.ptz.create_type('GotoHomePosition')
        self.requestHome.ProfileToken = self.media_profile.token

        # self.requestf = self.img.create_type('RelativeFocus')
        # self.requestf.ProfileToken = self.media_profile.token

        self.stop()

    # Stop pan, tilt and zoom
    def stop(self):
        self.requests.PanTilt = True
        self.requests.Zoom = True
        print(f"self.request:{self.requests}")
        self.ptz.Stop(self.requests)

    # Continuous move functions
    def perform_move(self, requestc):
        # Start continuous move
        ret = self.ptz.ContinuousMove(requestc)

    def move_continuous(self, pan, tilt, zoom=0):
        self.requestc.Velocity.PanTilt.x = pan
        self.requestc.Velocity.PanTilt.y = tilt
        self.requestc.Velocity.Zoom.x = zoom
        self.perform_move(self.requestc)
        # Sets preset set, query and and go to
    
    def call_home(self):
        self.ptz.GotoHomePosition(self.requestHome)

    def set_preset(self, name):
        self.requestp.PresetName = name
        self.requestp.PresetToken = '1'
        self.preset = self.ptz.SetPreset(
            self.requestp)  # returns the PresetToken

    def get_preset(self):
        self.ptzPresetsList = self.ptz.GetPresets(self.requestc)

    def goto_preset(self):
        self.requestg.PresetToken = '1'
        self.ptz.GotoPreset(self.requestg)

pygame.init()

def create_camera(camera):
    cam = None
    print('Loading', camera['name'])
    print('...')
    try:
        cam = PtzControl(camera['ip'], camera['port'], camera['user'], camera['password'])
        return cam
    except:
        print("could not load", camera['name'])
        return cam

def load_cameras():
    global cam1, cam2
    path = os.path.join(basedir, 'cameras.json')
    if os.path.exists(path):
        print('Loading cameras. Please wait for complete message...')
        print()
        f = open(path)
        cameras = json.load(f)
        cam1 = create_camera(cameras['cam1'])
        # cam2 = create_camera(cameras['cam2'])
        print('Camera load completed!')
        print("")
        print("")
    else:
        print('cameras.json file missing. Create a cameras.json file in this directory and restart')

def set_active_cam( controller):
    global active_cam, cam1, cam2, cam1Active, cam2Active
    if controller.get_button(4):
        if not cam1Active:
            print("cam1 active")
            active_cam = cam1
            cam1Active = True
            cam2Active = False
            controller.rumble(0,0.5,500)

    if controller.get_button(5):
        if not cam2Active:
            print("cam2 active")
            active_cam = cam2
            cam1Active = False
            cam2Active = True
            controller.rumble(0,0.5,500)


### CALLS
def call_continuous_movement():
    global stop_called, axis_left_tilt, axis_left_pan,axis_right_tilt, flip
    stop_called = False
    pan = (axis_left_pan * -1) if flip else (axis_left_pan * 1)
    tilt = (axis_left_tilt * 1) if flip else (axis_left_tilt * -1)
    zoom = (axis_right_tilt * 1) if flip else (axis_right_tilt * -1)

    pan = pan/2 if slow else pan
    tilt = tilt/2 if slow else tilt
    zoom = zoom/4 if slow else zoom
    active_cam.move_continuous(pan, tilt, zoom)

def call_home():
    global home_called
    if  home_called:
        active_cam.call_home()
        home_called = False

def call_stop():
    global stop_called
    if  stop_called:
        active_cam.stop()
        stop_called = False
    
def call_flip():
    global flip
    flip = not flip
        
def call_slow():
    global slow
    slow = not slow

### HANDLERS
def controller_handler(controller):
    global last_button_pressed, axis_left_pan, axis_left_tilt, axis_right_pan, axis_right_tilt, stop_called

    axis_left_x = 0.000
    axis_left_y = 0.000
    axis_right_y = 0.000

    if(controller.get_axis(0) > dead_zone or controller.get_axis(0) < -dead_zone):
        axis_left_x = round(controller.get_axis(0),3)
    if(controller.get_axis(1) > dead_zone or controller.get_axis(1) < -dead_zone):
        axis_left_y = round(controller.get_axis(1),3)
    if(controller.get_axis(3) > dead_zone or controller.get_axis(3) < -dead_zone):
        axis_right_y = round(controller.get_axis(3),3)

    if((axis_left_x != axis_left_pan) or (axis_left_y != axis_left_tilt) or (axis_right_y != axis_right_tilt)):
        axis_left_pan = axis_left_x
        axis_left_tilt = axis_left_y
        axis_right_tilt = axis_right_y
        # if( axis_left_x <= dead_zone and axis_left_x >= -dead_zone and axis_left_y <= dead_zone and axis_left_y >= -dead_zone and axis_right_y <= dead_zone and axis_right_y >= -dead_zone ):
        if(axis_left_pan == 0.0 and axis_right_pan == 0.0 and axis_right_tilt == 0.0):
            stop_called = True
            call_stop()
        # print(str(axis_left_pan) + ', ' + str(axis_left_tilt) + ', ' + str(axis_right_tilt))
        call_continuous_movement()

def button_selection(button):
    global is_running
    match button:
        case 0: #A
            call_flip()
        case 1: #B
            call_slow()
        case 2: #X
            pass
        case 3: #Y
            pass
        case 4: #LB
            pass
        case 5: #RB
            pass
        case 6: #Back
            is_running = False
        case 7: #Start
            is_running = True
        case 8: #LS
            call_home()
        case 9: #RS
            pass
        case _:
            pass

def dpad_actions(dpad):
    print(dpad)
    if(dpad[1] == 1):
        pass
    if(dpad[0] == 1):
        pass
    if(dpad[1] == -1):
        pass
    if(dpad[0] == -1):
        pass

def check_for_controller():
    print("checking for controller")
    pygame.joystick.init()
    if pygame.joystick.get_init():
        if pygame.joystick.get_count() > 0:
            print("joystick found...selecting")
            return pygame.joystick.Joystick(0)
        else:
            print("no joystick connected")
            None
    else:
        print("no joystick connected")
        None

def initialize():
    global controller, is_running
    print(f"TWEC PTZ Controller")
    print(f"Author: Josiah Maharaj")
    print(f"Last Updated: 20221022")
    print("############################################")
    print()
    print()
    sleep(1)

    load_cameras()
    controller = check_for_controller()
    if controller != None:
        is_running = True
        controller.rumble(0.5,1,0)
        print("Program active! Use LB or RB to select camera.")
        print("----------------------------------------------")
        print()
    else:
        print("No Controllers found. Quit and Reopen")


try:
    initialize()

    while is_running == True:
        for event in pygame.event.get():
            if event.type == pygame.JOYHATMOTION:
                dpad_actions(event.value)
            if event.type == pygame.QUIT:
                is_running = False
            if event.type == pygame.JOYBUTTONUP:
                button_selection(event.button)
        
        if controller != None:
            set_active_cam(controller)

        if(controller != None and active_cam != None):
            controller_handler(controller)
except:
    print("Error")