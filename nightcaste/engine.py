"""The engine is the main module of the game. It initializes all necessary
subsystems and runs the super loop"""
from behaviour import TurnBehaviourManager
from events import EventManager
from events import GUIAction
from entities import EntityManager
from nightcaste import __version__
from processes import ProcessManager
from processors import SystemManager
import game
import input
import logging
import pygame
import time
import utils

logger = logging.getLogger('engine')


def main():
    logger.info('Nightcaste v%s', __version__)

    game_config = utils.load_config('config/nightcaste.json')

    realtime = True
    pygame.init()
    event_manager = EventManager()
    entity_manager = EntityManager()
    behaviour_manager = TurnBehaviourManager(
        event_manager,
        entity_manager,
        game_config['behaviours'])
    system_manager = SystemManager(
        event_manager,
        entity_manager,
        game_config)
    process_manager = ProcessManager(entity_manager, event_manager)
    input_controller = input.InputController(
        not realtime, event_manager, entity_manager)
    window = create_window(event_manager, entity_manager, system_manager)
    request_close = False
    prev_time = time.time()
    lag = 0.0
    # fps_time = 0.0
    # fps_frames = 0
    SEC_PER_UPDATE = 0.01
    MIN_FRAME_TIME = 1.0 / 60

    # TODO do not throw an event here, instead configure a default view and
    # throw ViewChnaged when the engine is initialized
    event_manager.throw_new(GUIAction.MenuOpen)
    while window.is_active() and not request_close:
        current_time = time.time()
        time_delta = current_time - prev_time
        prev_time = current_time
        lag += time_delta

        while (lag >= SEC_PER_UPDATE):
            request_close = input_controller.update(round, SEC_PER_UPDATE)
            if game.status != game.G_PAUSED:
                behaviour_manager.update(round, SEC_PER_UPDATE)
                event_manager.process_events()

            system_manager.update(round, SEC_PER_UPDATE)
            event_manager.process_events()

            process_manager.update(SEC_PER_UPDATE)
            event_manager.process_events()

            lag -= SEC_PER_UPDATE

        window.render()
        render_time = time.time() - current_time
        time.sleep(max(MIN_FRAME_TIME - render_time, 0))
        """
        fps_time += time_delta
        fps_frames += 1
        if fps_time >= 1.0:
            print 'FPS: %d' % (fps_frames)
            fps_time, fps_frames = (0.0, 0)
        """
    pygame.quit()
    return 0


def create_window(event_manager, entity_manager, system_manager):
    gui_config = utils.load_config('config/gui.json')
    mngr_config = gui_config['window_manager']
    window_manager_class = utils.class_for_name(mngr_config[0], mngr_config[1])
    window_manager = window_manager_class(event_manager, entity_manager,
                                          system_manager,
                                          gui_config)
    window = window_manager.create("nightcaste")

    return window
