from msilib.schema import ControlCondition
from operator import itemgetter
import time
import pygame
import pygame_gui
from onvif import ONVIFCamera

IP = '192.168.1.118'
PORT = 8000
USER = 'admin'
PASS = 'admin'

dead_zone = 0.09
last_button_pressed = "None"
flip = False
slow = False
axis_left_pan = 0.000
axis_left_tilt = 0.000
axis_right_pan = 0.000
axis_right_tilt = 0.000

ptz = [0.000, 0.000, 0.000]
active_cam = None
cam1 = None
cam2 = None
cam3 = None
cam4 = None

is_running = True
controller = None

stop_called = True
home_called = False

class PtzControl(object):
    def __init__(self, ip,  port, user, password):
        super(PtzControl, self,).__init__()
        self.mycam = ONVIFCamera(ip, port, user, password, wsdl_dir='wsdl')
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

        # get absoluteMove request -- requesta
        self.requesta = self.ptz.create_type('AbsoluteMove')
        self.requesta.ProfileToken = self.media_profile.token
        if self.requesta.Position is None:
            self.requesta.Position = self.ptz.GetStatus(
                {'ProfileToken': self.media_profile.token}).Position
        if self.requesta.Speed is None:
            self.requesta.Speed = self.ptz.GetStatus(
                {'ProfileToken': self.media_profile.token}).Position

        # get relativeMove request -- requestr
        self.requestr = self.ptz.create_type('RelativeMove')
        self.requestr.ProfileToken = self.media_profile.token
        if self.requestr.Translation is None:
            self.requestr.Translation = self.ptz.GetStatus(
                {'ProfileToken': self.media_profile.token}).Position
            self.requestr.Translation.PanTilt.space = ptz_configuration_options.Spaces.RelativePanTiltTranslationSpace[
                0].URI
            self.requestr.Translation.Zoom.space = ptz_configuration_options.Spaces.RelativeZoomTranslationSpace[
                0].URI
        if self.requestr.Speed is None:
            self.requestr.Speed = self.ptz.GetStatus(
                {'ProfileToken': self.media_profile.token}).Position

        self.requests = self.ptz.create_type('Stop')
        self.requests.ProfileToken = self.media_profile.token
        self.requestp = self.ptz.create_type('SetPreset')
        self.requestp.ProfileToken = self.media_profile.token
        self.requestg = self.ptz.create_type('GotoPreset')
        self.requestg.ProfileToken = self.media_profile.token
        self.requestHome = self.ptz.create_type('GotoHomePosition')
        self.requestHome.ProfileToken = self.media_profile.token
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
pygame.font.init()

pygame.display.set_caption('XBOX PTZ Controller')
surface = pygame.display.set_mode((400,500)) 

background = pygame.Surface((400,500))
background.fill(pygame.Color('#000000'))

manager = pygame_gui.UIManager((400,500))

clock = pygame.time.Clock()

def set_active_cam(dpad, controller):
    global active_cam, cam1, cam2, cam3, cam4
    if(dpad[1] == 1):
        print("cam1 active")
        cam1 = PtzControl('192.168.1.118',8000,'admin','admin')
        active_cam = cam1
        controller.rumble(0,0.5,500)
    if(dpad[0] == 1):
        print("cam2 active")
        active_cam = cam2
        controller.rumble(0,0.5,500)
    if(dpad[1] == -1):
        print("cam3 active")
        active_cam = cam3
        controller.rumble(0,0.5,500)
    if(dpad[0] == -1):
        print("cam4 active")
        active_cam = cam4
        controller.rumble(0,0.5,500)
def create_font(t,size=15,color=(255,255,255), bold=False,italic=False):
    font = pygame.font.SysFont("Arial", size, bold=bold, italic=italic)
    text = font.render(t, True, color)
    return text

def call_continuous_movement():
    global stop_called, axis_left_tilt, axis_left_pan,axis_right_tilt, flip
    stop_called = False
    pan = (axis_left_pan * -1) if flip else (axis_left_pan * 1)
    tilt = (axis_left_tilt * 1) if flip else (axis_left_tilt * -1)
    zoom = (axis_right_tilt * 1) if flip else (axis_right_tilt * -1)

    pan = pan/2 if slow else pan
    tilt = tilt/2 if slow else tilt
    zoom = zoom/2 if slow else zoom
    active_cam.move_continuous(pan, tilt, zoom)

def call_home():
    active_cam.call_home()

def call_stop():
    global stop_called
    if not stop_called:
        active_cam.stop()
        print('Stopped')
        stop_called = True
    
def controller_handler(controller):
    global last_button_pressed, axis_left_pan, axis_left_tilt, axis_right_pan, axis_right_tilt, cam

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
            call_stop()
        print(str(axis_left_pan) + ', ' + str(axis_left_tilt) + ', ' + str(axis_right_tilt))
        call_continuous_movement()

    # axis_right_x = round(controller.get_axis(3),3)
    if controller.get_button(0):
        last_button_pressed = "A"
        print("BUTTON A")

    if controller.get_button(1):
        last_button_pressed = "B"
        print("BUTTON B")

    if controller.get_button(2):
        last_button_pressed = "X"
        print("BUTTON X")

    if controller.get_button(3):
        last_button_pressed = "Y"
        print("BUTTON Y")

    if controller.get_button(4):
        last_button_pressed = "LB"
        print("BUTTON LB")

    if controller.get_button(5):
        last_button_pressed = "RB"
        print("BUTTON RB")

    if controller.get_button(6):
        print("BUTTON OPT")
        is_running = False
        controller.quit()
    
    if controller.get_button(7):
        last_button_pressed = "MENU"
        print("BUTTON MENU")

    if controller.get_button(8):
        print("LT Pressed")
        call_home()
    if controller.get_button(10):
        print("D Pad")

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

def show_selected_camera():
    selected = create_font("Selected Camera: " + last_button_pressed)
    surface.blit(selected, (10,70))

controller = check_for_controller()
power = controller.get_power_level
# print(power)
# time.sleep(3)
controller.rumble(0.5,1,0)

def display_controller_info():
    name = create_font("Connected: " + controller.get_name())
    number_axes = create_font("No. Axes: " + str(controller.get_numaxes()))
    surface.blit(name, (10,30))
    surface.blit(number_axes, (10,50))

title = create_font('XBox PTZ Mapping Controller (TWEC)',20, bold=True)

# controller = pygame.joystick.Joystick(0)

while is_running == True:
    time_delta = clock.tick(60)/1000.0
    for event in pygame.event.get():
        if event.type == pygame.JOYHATMOTION:
            set_active_cam(event.value, controller)
        if event.type == pygame.QUIT:
            is_running = False

        manager.process_events(event)

    manager.update(time_delta)

    if(controller != None and active_cam != None):
        controller_handler(controller)

    surface.blit(background, (0,0))
    surface.blit(title,(10,10))
    show_selected_camera()
    display_controller_info()
    manager.draw_ui(surface)

    pygame.display.update()

            