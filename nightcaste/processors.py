"""The module contains the event processors. An event processor must register
itself in the EventManager in order to retrieve the events to process"""
from collision import QTreeCollisionManager
from events import FrameworkEvent
from events import GameAction
from events import GameEvent
from events import GUIAction
from events import GUIEvent
from events import InputEvent
from mapcreation import MapManager
from pygame import Rect
from sound import SoundBank
import game
import input
import logging
import utils
import math


class SystemManager:
    """Creates, configures and manages all GameSystems.

    Args:
        event_manager(EventManager): The event manager will be pass to all new
            systems.
        entity_manager (EntityManager): The entity manager will be passed to all
            systems.
        config (dict): (Optitonally) Create new systems from config.

    """

    def __init__(self, event_manager, entity_manager, config=None):
        self.systems = []
        self.event_manager = event_manager
        self.entity_manager = entity_manager
        if config is not None:
            self.configure(config)

    def configure(self, config):
        """Configure systems based on the given config.

        Args:
            config (dict):
                {
                    'systems': [{
                        'impl': 'systemClass',
                        'config': {systemparam: args}
                    }]
                }
        """
        if 'systems' in config:
            for system_config in config['systems']:
                self.add_system_by_config(system_config)

    def add_system(self, system):
        """Adds a system and calls its register function"""
        self.systems.append(system)
        # TODO rename to more general intialize
        system.register()

    def add_system_by_config(self, system_config):
        """Create and initialize a new system. The system has to be class in the
        module processors."""
        impl = system_config['impl']
        system_class = utils.class_for_name(impl[0], impl[1])
        system = system_class(self.event_manager, self.entity_manager)
        if 'config' in system_config:
            system.configure(system_config['config'])
        self.add_system(system)

    def update(self, round, delta_time):
        """Calls update on all systems."""
        for system in self.systems:
            system.update(round, delta_time)


class EventProcessor(object):
    """Base class for all processors.

        Args:
            event_manager (EventManager): The event manager for enqueuing new
                events.
            entity_manager (EntityManager): The entity manager for creating,
                destroying entities and access their properties

    """

    def __init__(self, event_manager, entity_manager):
        self.event_manager = event_manager
        self.entity_manager = entity_manager

    def configure(self, config):
        """Configure a special system parameters from a configuration or json
        structure."""
        pass

    def update(self, round, delta_time):
        pass

    def register(self):
        pass

    def unregister(self):
        pass

    def _register(self, event_type, process_function):
        self.event_manager.register_listener(event_type, process_function)

    def _unregister(self, event_type, process_function):
        self.event_manager.remove_listener(event_type, process_function)

    def _create_event(self, event_type):
        return self.event_manager.create(event_type)

    def _throw_event(self, event):
        self.event_manager.throw(event)

    def _throw_new_event(self, event_type, data=None):
        self.event_manager.throw_new(event_type, data)

    def __str__(self):
        return self.__class__.__name__


class InputProcessor(EventProcessor):

    logger = logging.getLogger('processors.InputProcessor')

    def register(self):
        self._register(GUIEvent.ViewChanged, self.on_view_changed)

    def unregister(self):
        self._unregister(GUIEvent.ViewChanged, self.on_view_changed)

    def on_view_changed(self, event):
        if self._is_responsible_for(event.active_view):
            self._register(InputEvent.KeyPressed, self.on_key_pressed)
        else:
            self._unregister(InputEvent.KeyPressed, self.on_key_pressed)

    def on_key_pressed(self, event):
        action = self._map_key_to_action(event.keycode)
        self.logger.debug('Mapped key %s to %s', event.keycode, action)
        if action is not None:
            self._throw_event(action)


class GameInputProcessor(InputProcessor):
    """Handle all key inputs if the player is in the world and not showing a
    menu."""

    def _is_responsible_for(self, view_name):
        return view_name == 'game_view'

    def _map_key_to_action(self, keycode):
        return None


class MenuInputProcessor(InputProcessor):

    def _is_responsible_for(self, view_name):
        return view_name == 'main_menu'

    def _map_key_to_action(self, keycode):
        if keycode == input.K_ENTER:
            return self._create_event(GameAction.WorldEnter)
        return None


class MovementSystem(EventProcessor):

    logger = logging.getLogger('processors.MovementProcessor')

    def register(self):
        self._register(GameEvent.MapChanged, self.on_map_changed)

    def unregister(self):
        self._unregister(GameEvent.MapChanged, self.on_map_changed)

    def __init__(self, event_manager, entity_manager, no_collision=False):
        EventProcessor.__init__(self, event_manager, entity_manager)
        self.collision_manager = QTreeCollisionManager()
        self.moving_entities = {}

    def apply(self, entity, direction, distance, position, collidable):
        dx, dy = direction.get_dx(distance), direction.get_dy(distance)
        collides = False
        if collidable is not None:
            # Convert -0.12 to -1, and 0.45 to 1
            predicted_dx = math.copysign(math.ceil(math.fabs(dx)), dx)
            predicted_dy = math.copysign(math.ceil(math.fabs(dy)), dy)
            rect = collidable.move(predicted_dx, predicted_dy)
            collisions = self.collision_manager.collide_rect(entity, rect)
            if len(collisions) > 0:
                # throw event for each colliding entity
                collides = True
                self.logger.debug('Entity %s collided', entity)

        if not collides:
            position.move(dx, dy)
            if collidable is not None:
                collidable.set_position(position.x, position.y)
                self.collision_manager.move(entity)

    def update(self, round, delta):
        moving_entities = self.entity_manager.get_all('Input')
        entity_positions = self.entity_manager.get_all('Position')
        entity_movement = self.entity_manager.get_all('Movement')
        entity_collidables = self.entity_manager.get_all('Colliding')
        for entity, inputcomp in moving_entities.items():
            # TODO: Make an Animation Processor or think of a more elegant
            # solution for animation handling
            sprite = self.entity_manager.get(entity, "Sprite")
            if inputcomp.direction.direction != 0:
                position = entity_positions[entity]
                movement = entity_movement[entity]
                collidable = entity_collidables.get(entity)
                sprite.animate("walk")
                self.apply(
                    entity,
                    inputcomp.direction,
                    movement.speed * delta,
                    position,
                    collidable)
            else:
                sprite.animate("idle")

    def on_map_changed(self, event):
        map = self.entity_manager.current_map
        # TODO: Map should countain bounds
        collidables = self.entity_manager.get_all('Colliding')
        self.collision_manager.fill(Rect(0, 0, 3200, 4480), collidables)


class WorldInitializer(EventProcessor):
    """Registers to WorldEnteredEvent and performs necessary world
    initialization."""

    def register(self):
        self._register(GameAction.WorldEnter, self.on_world_enter)

    def unregister(self):
        self._unregister(GameAction.WorldEnter, self.on_world_enter)

    def configure(self, config):
        self.start_time = config.get('start_time', 0)

    def on_world_enter(self, event):
        game.time = self.start_time
        self.entity_manager.player = self.entity_manager.new_from_blueprint(
            'game.player')
        # TODO let the entity manager throw the event
        entity_created = self._create_event(FrameworkEvent.EntityCreated)
        entity_created.entity = self.entity_manager.player
        self._throw_event(entity_created)
        map_change = self._create_event(GameAction.MapChange)
        map_change.name = 'world'
        map_change.level = 0
        map_change.type = 'world'
        self._throw_event(map_change)


class MapChangeProcessor(EventProcessor):
    """Listens on MapChange Events and uses chnages or generates the maps
    accordingly."""
    logger = logging.getLogger('processors.MapChangeProcessor')

    def register(self):
        self._register(GameAction.MapChange, self.on_map_change)

    def unregister(self):
        self._unregister(GameAction.MapChange, self.on_map_change)

    def __init__(self, event_manager, entity_manager):
        EventProcessor.__init__(self, event_manager, entity_manager)
        self.map_manager = MapManager(entity_manager)

    def on_map_change(self, event):
        if event.level is None:
            event.level = 0
        self.logger.debug(
            'Changing to Map %s - %d',
            event.name,
            event.level)
        new_map = self.map_manager.get_map(event.name,
                                           event.level,
                                           event.get('type', 'dungeon'))
        # TODO fix absolute positioning
        # Since the entry point is stored in the map the position of the player
        # could also be changed on GameEvent.MapChanged
        entry_point = self.entity_manager.get(new_map, 'Map').entry
        move_action = self._create_event(GameAction.MoveAction)
        move_action.entity = self.entity_manager.player
        move_action.dx = entry_point[0]
        move_action.dy = entry_point[1]
        move_action.absolute = 1
        self._throw_event(move_action)
        self.change_map(new_map)

    def change_map(self, new_map):
        """Changes the current map with the specified map."""
        if self.entity_manager.current_map is not None:
            new_mc = self.entity_manager.get(new_map, 'Map')
            cur_mc = self.entity_manager.get(
                self.entity_manager.current_map, 'Map')
            new_mc.parent = self.entity_manager.current_map
            cur_mc.add_child(new_map)
        self.entity_manager.current_map = new_map
        self._throw_new_event(GameEvent.MapChanged)


class SpriteProcessor(EventProcessor):
    """Initializes sprites of created entites with sprite components. Detects
    moved Sprites and updates their dirty flag."""
    logger = logging.getLogger('processors.SpriteProcessor')

    def __init__(self, event_manager, entity_manager, sprite_manager):
        EventProcessor.__init__(self, event_manager, entity_manager)
        self.sprite_manager = sprite_manager

    def register(self):
        self._register(FrameworkEvent.EntityCreated, self.on_entity_created)
        self._register(GameEvent.EntityMoved, self.on_entity_moved)

    def unregister(self):
        self._unregister(FrameworkEvent.EntityCreated, self.on_entity_created)
        self._unregister(GameEvent.EntityMoved, self.on_entity_moved)

    def on_entity_created(self, event):
        entity = event.entity
        sprite = self.entity_manager.get(entity, 'Sprite')
        if sprite is not None:
            self.sprite_manager.initialize_sprite(sprite)

    def on_entity_moved(self, event):
        entity = event.entity
        sprite = self.entity_manager.get(entity, 'Sprite')
        if sprite is not None:
            self.logger.debug('Set sprite dirty %s', sprite)
            sprite.dirty = 1

    def update(self, round, delta_time):
        for entity, sprite in self.entity_manager.get_all(
                'Sprite').items():
            sprite.update(round, delta_time)


class UseEntityProcessor(EventProcessor):
    """ Listens for UseEntity Events, determines Target Entity and throws its
    Use-Event """

    def __init__(self, event_manager, entity_manager):
        EventProcessor.__init__(self, event_manager, entity_manager)
        self.collision_manager = QTreeCollisionManager()

    def register(self):
        self._register(GameAction.UseEntityAction, self.on_use_entity)

    def unregister(self):
        self._unregister(GameAction.UseEntityAction, self.on_use_entity)

    def on_use_entity(self, event):
        user = self.entity_manager.get(event.user, 'Position')
        user_colliding = self.entity_manager.get(event.user, 'Colliding')
        target = (user.x, user.y)
        useables = self.entity_manager.get_all('Useable')
        useable_rects = {}
        for entity in useables:
            pos = self.entity_manager.get(entity, 'Position')
            useable_rects[entity] = Rect(pos.x-16, pos.y-16, 32, 32)
        self.collision_manager.fill(Rect(0, 0, 3200, 4480), useable_rects)
        collisions = self.collision_manager.collide_rect(
            event.user, user_colliding)

        if (len(collisions) > 0):
            action = getattr(GameAction, useables[collisions[0]].useEvent)
            self._throw_new_event(action, {'usedEntity': collisions[0]})


class TransitionProcessor(EventProcessor):
    """ Converts an Event into MapChange Events with the entity's MapTransition
    Component """

    def register(self):
        self._register(GameAction.MapTransition, self.on_map_transition)

    def unregister(self):
        self._unregister(GameAction.MapTransition, self.on_map_transition)

    def on_map_transition(self, event):
        target = self.entity_manager.get(event.usedEntity, 'MapTransition')
        map_change = self._create_event(GameAction.MapChange)
        map_change.name = target.target_map
        map_change.level = target.target_level
        self._throw_event(map_change)


class ViewProcessor(EventProcessor):
    """Listen on events which requires the view to react in some way. Therefore,
    the view has to provide methods to change its state."""

    def __init__(self, event_manager, entity_manager, window):
        EventProcessor.__init__(self, event_manager, entity_manager)
        self.window = window

    def register(self):
        self._register(GameAction.MapChange, self.on_map_change)
        self._register(GUIAction.MenuOpen, self.on_menu_open)
        self._register(GameEvent.EntityMoved, self.on_entity_moved)

    def unregister(self):
        self._unregister(GameAction.MapChange, self.on_map_change)
        self._unregister(GUIAction.MenuOpen, self.on_menu_open)
        self._unregister(GameEvent.EntityMoved, self.on_entity_moved)

    def on_map_change(self, event):
        # TODO: make view active on world enter and handle map updating with a
        # simple map.dirty flag
        if self.window.show('game_view'):
            # TODO let view_controller throw the event?
            view_changed = self._create_event(GUIEvent.ViewChanged)
            view_changed.active_view = 'game_view'
            self._throw_event(view_changed)

    def on_menu_open(self, event):
        if self.window.show('main_menu'):
            view_changed = self._create_event(GUIEvent.ViewChanged)
            view_changed.active_view = 'main_menu'
            self._throw_event(view_changed)

    def on_entity_moved(self, event):
        # Update the game view (calculates viewport) if the player has moved
        if event.entity == self.entity_manager.player:
            self.window.update_view('game_view')


class SoundSystem(EventProcessor):

    logger = logging.getLogger('processors.SoundSystem')

    def configure(self, config):
        self.sound_bank = SoundBank(config['sound_path'])

    def play(self, key):
        sound = self.sound_bank.get(key)
        if sound is not None:
            sound.play(-1)
        else:
            self.logger.error('Sound %s does not exits in sound bank.', key)


class PocSoundSystem(SoundSystem):

    def register(self):
        self._register(GUIAction.MenuOpen, self.on_menu_open)

    def on_menu_open(self, event):
        self.play('nightcaste_main.wav')


class GameTimeSystem(EventProcessor):

    def __init__(self, event_manager, entity_manager):
        super(GameTimeSystem, self).__init__(event_manager, entity_manager)
        self.time_multi = 1.0

    def configure(self, config):
        self.time_multi = config['time_multi']

    def update(self, round, delta_time):
        if game.status != game.G_PAUSED:
            game.time += delta_time * self.time_multi
