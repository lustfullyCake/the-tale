# coding: utf-8
import copy
import datetime

from dext.utils.decorators import nested_commit_on_success

from textgen.words import Noun

from common.postponed_tasks import postponed_task, POSTPONED_TASK_LOGIC_RESULT
from common.utils.enum import create_enum

from game.balance import constants as c

from game.map.places.storage import places_storage
from game.mobs.storage import MobsDatabase
from game.persons.storage import persons_storage

from game.heroes.models import PREFERENCE_TYPE
from game.heroes.habilities import ABILITIES
from game.heroes.bag import SLOTS_LIST


CHOOSE_HERO_ABILITY_STATE = create_enum('CHOOSE_HERO_ABILITY_STATE', ( ('UNPROCESSED', 0, u'в очереди'),
                                                                       ('PROCESSED', 1, u'обработана'),
                                                                       ('WRONG_ID', 2, u'неверный идентификатор способности'),
                                                                       ('NOT_IN_CHOICE_LIST', 3, u'способность недоступна для выбора'),
                                                                       ('NOT_FOR_PLAYERS', 4, u'способность не для игроков'),
                                                                       ('NO_DESTINY_POINTS', 5, u'нехватает очков'),
                                                                       ('ALREADY_CHOOSEN', 6, u'способность уже выбрана') ) )

@postponed_task
class ChooseHeroAbilityTask(object):

    TYPE = 'choose-hero-ability'

    def __init__(self, hero_id, ability_id, state=CHOOSE_HERO_ABILITY_STATE.UNPROCESSED):
        self.hero_id = hero_id
        self.ability_id = ability_id
        self.state = state

    def __eq__(self, other):
        return (self.hero_id == other.hero_id and
                self.ability_id == other.ability_id and
                self.state == other.state )

    def serialize(self):
        return { 'hero_id': self.hero_id,
                 'ability_id': self.ability_id,
                 'state': self.state}

    @classmethod
    def deserialize(cls, data):
        return cls(**data)

    @property
    def uuid(self): return self.hero_id

    @property
    def response_data(self): return {}

    @property
    def error_message(self): return CHOOSE_HERO_ABILITY_STATE.CHOICES[self.state][1]

    @nested_commit_on_success
    def process(self, main_task, storage):

        hero = storage.heroes[self.hero_id]

        if self.ability_id not in ABILITIES:
            self.state = CHOOSE_HERO_ABILITY_STATE.WRONG_ID
            main_task.comment = u'no ability with id "%s"' % self.ability_id
            return POSTPONED_TASK_LOGIC_RESULT.ERROR

        choices = hero.get_abilities_for_choose()

        if self.ability_id not in [choice.get_id() for choice in choices]:
            self.state = CHOOSE_HERO_ABILITY_STATE.NOT_IN_CHOICE_LIST
            main_task.comment = u'ability not in choices list: %s' % self.ability_id
            return POSTPONED_TASK_LOGIC_RESULT.ERROR

        ability = ABILITIES[self.ability_id]

        if not ability.AVAILABLE_TO_PLAYERS:
            self.state = CHOOSE_HERO_ABILITY_STATE.NOT_FOR_PLAYERS
            main_task.comment = u'ability "%s" does not available to players' % self.ability_id
            return POSTPONED_TASK_LOGIC_RESULT.ERROR

        if hero.destiny_points <= 0:
            self.state = CHOOSE_HERO_ABILITY_STATE.NO_DESTINY_POINTS
            main_task.comment = 'no destiny points'
            return POSTPONED_TASK_LOGIC_RESULT.ERROR

        if hero.abilities.has(self.ability_id):
            self.state = CHOOSE_HERO_ABILITY_STATE.ALREADY_CHOOSEN
            main_task.comment = 'ability has been already choosen'
            return POSTPONED_TASK_LOGIC_RESULT.ERROR

        hero.abilities.add(self.ability_id)

        hero.destiny_points -= 1
        hero.destiny_points_spend += 1

        with nested_commit_on_success():
            storage.save_hero_data(hero.id)

        self.state = CHOOSE_HERO_ABILITY_STATE.PROCESSED

        return POSTPONED_TASK_LOGIC_RESULT.SUCCESS


CHANGE_HERO_TASK_STATE = create_enum('CHANGE_HERO_TASK_STATE', ( ('UNPROCESSED', 0, u'в очереди'),
                                                                 ('PROCESSED', 1, u'обработана') ) )

@postponed_task
class ChangeHeroTask(object):

    TYPE = 'change-hero'

    def __init__(self, hero_id, name, race, gender, state=CHANGE_HERO_TASK_STATE.UNPROCESSED):
        self.hero_id = hero_id
        self.name = name
        self.race = race
        self.gender = gender
        self.state = state

    def __eq__(self, other):
        return (self.hero_id == other.hero_id and
                self.name == other.name and
                self.race == other.race and
                self.gender == other.gender and
                self.state == other.state )

    def serialize(self):
        return { 'hero_id': self.hero_id,
                 'name': self.name.serialize(),
                 'race': self.race,
                 'gender': self.gender,
                 'state': self.state}

    @classmethod
    def deserialize(cls, data):
        kwargs = copy.deepcopy(data)
        kwargs['name'] = Noun.deserialize(kwargs['name'])
        return cls(**kwargs)

    @property
    def uuid(self): return self.hero_id

    @property
    def response_data(self): return {}

    @property
    def error_message(self): return CHANGE_HERO_TASK_STATE.CHOICES[self.state][1]

    @nested_commit_on_success
    def process(self, main_task, storage):

        hero = storage.heroes[self.hero_id]

        hero.normalized_name = self.name
        hero.gender = self.gender
        hero.race = self.race

        with nested_commit_on_success():
            storage.save_hero_data(hero.id)

        self.state = CHANGE_HERO_TASK_STATE.PROCESSED

        return POSTPONED_TASK_LOGIC_RESULT.SUCCESS


CHOOSE_PREFERENCES_TASK_STATE = create_enum('CHOOSE_PREFERENCES_TASK_STATE', ( ('UNPROCESSED', 0, u'в очереди'),
                                                                               ('PROCESSED', 1, u'обработана'),
                                                                               ('COOLDOWN', 2, u'смена способности недоступна'),
                                                                               ('LOW_LEVEL', 3, u'низкий уровень героя'),
                                                                               ('UNAVAILABLE_PERSON', 4, u'персонаж недоступен'),
                                                                               ('OUTGAME_PERSON', 5, u'персонаж выведен из игры'),
                                                                               ('UNSPECIFIED_PREFERENCE', 6, u'предпочтение неуказано'),
                                                                               ('UNKNOWN_ENERGY_REGENERATION_TYPE', 7, u'неизвестный тип восстановления энергии'),
                                                                               ('UNKNOWN_MOB', 8, u'неизвестный тип монстра'),
                                                                               ('LARGE_MOB_LEVEL', 9, u'слишком сильный монстр'),
                                                                               ('UNKNOWN_PLACE', 10, u'неизвестное место'),
                                                                               ('ENEMY_AND_FRIEND', 11, u'персонаж одновременно и друг и враг'),
                                                                               ('UNKNOWN_PERSON', 12, u'неизвестный персонаж'),
                                                                               ('UNKNOWN_EQUIPMENT_SLOT', 13, u'неизвестный тип экипировки'),
                                                                               ('UNKNOWN_PREFERENCE', 14, u'неизвестный тип предпочтения'),) )


@postponed_task
class ChoosePreferencesTask(object):

    TYPE = 'choose-hero-preferences'

    def __init__(self, hero_id, preference_type, preference_id, state=CHOOSE_PREFERENCES_TASK_STATE.UNPROCESSED):
        self.hero_id = hero_id
        self.preference_type = preference_type
        self.preference_id = preference_id
        self.state = state

    def __eq__(self, other):
        return (self.hero_id == other.hero_id and
                self.preference_type == other.preference_type and
                self.preference_id == other.preference_id and
                self.state == other.state )

    def serialize(self):
        return { 'hero_id': self.hero_id,
                 'preference_type': self.preference_type,
                 'preference_id': self.preference_id,
                 'state': self.state }

    @classmethod
    def deserialize(cls, data):
        return cls(**data)

    @property
    def uuid(self): return self.hero_id

    @property
    def response_data(self): return {}

    @property
    def error_message(self): return CHOOSE_PREFERENCES_TASK_STATE.CHOICES[self.state][1]

    def process(self, main_task, storage):

        hero = storage.heroes[self.hero_id]

        if not hero.preferences.can_update(self.preference_type, datetime.datetime.now()):
            main_task.comment = u'blocked since time delay'
            self.state = CHOOSE_PREFERENCES_TASK_STATE.COOLDOWN
            return POSTPONED_TASK_LOGIC_RESULT.ERROR

        if self.preference_type == PREFERENCE_TYPE.ENERGY_REGENERATION_TYPE:

            if hero.level < c.CHARACTER_PREFERENCES_ENERGY_REGENERATION_TYPE_LEVEL_REQUIRED:
                main_task.comment = u'hero level < required level (%d < %d)' % (hero.level, c.CHARACTER_PREFERENCES_ENERGY_REGENERATION_TYPE_LEVEL_REQUIRED)
                self.state = CHOOSE_PREFERENCES_TASK_STATE.LOW_LEVEL
                return POSTPONED_TASK_LOGIC_RESULT.ERROR

            energy_regeneration_type = int(self.preference_id) if self.preference_id is not None else None

            if energy_regeneration_type is None:
                main_task.comment = u'energy regeneration preference can not be None'
                self.state = CHOOSE_PREFERENCES_TASK_STATE.UNSPECIFIED_PREFERENCE
                return POSTPONED_TASK_LOGIC_RESULT.ERROR

            if energy_regeneration_type not in c.ANGEL_ENERGY_REGENERATION_DELAY:
                main_task.comment = u'unknown energy regeneration type: %s' % (energy_regeneration_type, )
                self.state = CHOOSE_PREFERENCES_TASK_STATE.UNKNOWN_ENERGY_REGENERATION_TYPE
                return POSTPONED_TASK_LOGIC_RESULT.ERROR

            hero.preferences.energy_regeneration_type = energy_regeneration_type
            hero.preferences.energy_regeneration_type_changed_at = datetime.datetime.now()


        elif self.preference_type == PREFERENCE_TYPE.MOB:

            mob_id = self.preference_id

            if mob_id is not None:

                if hero.level < c.CHARACTER_PREFERENCES_MOB_LEVEL_REQUIRED:
                    main_task.comment = u'hero level < required level (%d < %d)' % (hero.level, c.CHARACTER_PREFERENCES_MOB_LEVEL_REQUIRED)
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.LOW_LEVEL
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if self.preference_id not in MobsDatabase.storage():
                    main_task.comment = u'unknown mob id: %s' % (self.preference_id, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.UNKNOWN_MOB
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                mob = MobsDatabase.storage()[self.preference_id]

                if hero.level < mob.level:
                    main_task.comment = u'hero level < mob level (%d < %d)' % (hero.level, mob.level)
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.LARGE_MOB_LEVEL
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

            hero.preferences.mob_id = mob_id
            hero.preferences.mob_changed_at = datetime.datetime.now()

        elif self.preference_type == PREFERENCE_TYPE.PLACE:

            place_id = int(self.preference_id) if self.preference_id is not None else None

            if place_id is not None:

                if hero.level < c.CHARACTER_PREFERENCES_PLACE_LEVEL_REQUIRED:
                    main_task.comment = u'hero level < required level (%d < %d)' % (hero.level, c.CHARACTER_PREFERENCES_PLACE_LEVEL_REQUIRED)
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.LOW_LEVEL
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if place_id not in places_storage:
                    main_task.comment = u'unknown place id: %s' % (place_id, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.UNKNOWN_PLACE
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

            hero.preferences.place_id = place_id
            hero.preferences.place_changed_at = datetime.datetime.now()

        elif self.preference_type == PREFERENCE_TYPE.FRIEND:

            friend_id = int(self.preference_id) if self.preference_id is not None else None

            if friend_id is not None:
                if hero.level < c.CHARACTER_PREFERENCES_FRIEND_LEVEL_REQUIRED:
                    main_task.comment = u'hero level < required level (%d < %d)' % (hero.level, c.CHARACTER_PREFERENCES_FRIEND_LEVEL_REQUIRED)
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.LOW_LEVEL
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if hero.preferences.enemy_id == friend_id:
                    main_task.comment = u'try set enemy as a friend (%d)' % (friend_id, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.ENEMY_AND_FRIEND
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if friend_id not in persons_storage:
                    main_task.comment = u'unknown person id: %s' % (friend_id, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.UNKNOWN_PERSON
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if persons_storage[friend_id].out_game:
                    main_task.comment = u'person was moved out game: %s' % (friend_id, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.OUTGAME_PERSON
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

            hero.preferences.friend_id = friend_id
            hero.preferences.friend_changed_at = datetime.datetime.now()

        elif self.preference_type == PREFERENCE_TYPE.ENEMY:

            enemy_id = int(self.preference_id) if self.preference_id is not None else None

            if enemy_id is not None:
                if hero.level < c.CHARACTER_PREFERENCES_ENEMY_LEVEL_REQUIRED:
                    main_task.comment = u'hero level < required level (%d < %d)' % (hero.level, c.CHARACTER_PREFERENCES_ENEMY_LEVEL_REQUIRED)
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.LOW_LEVEL
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if hero.preferences.friend_id == enemy_id:
                    main_task.comment = u'try set friend as an enemy (%d)' % (enemy_id, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.ENEMY_AND_FRIEND
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if enemy_id not in persons_storage:
                    main_task.comment = u'unknown person id: %s' % (enemy_id, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.UNKNOWN_PERSON
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if persons_storage[enemy_id].out_game:
                    main_task.comment = u'person was moved out game: %s' % (enemy_id, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.OUTGAME_PERSON
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR


            hero.preferences.enemy_id = enemy_id
            hero.preferences.enemy_changed_at = datetime.datetime.now()

        elif self.preference_type == PREFERENCE_TYPE.EQUIPMENT_SLOT:

            equipment_slot = self.preference_id

            if equipment_slot is not None:

                if hero.level < c.CHARACTER_PREFERENCES_EQUIPMENT_SLOT_LEVEL_REQUIRED:
                    main_task.comment = u'hero level < required level (%d < %d)' % (hero.level, c.CHARACTER_PREFERENCES_EQUIPMENT_SLOT_LEVEL_REQUIRED)
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.LOW_LEVEL
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

                if self.preference_id not in SLOTS_LIST:
                    main_task.comment = u'unknown equipment slot: %s' % (equipment_slot, )
                    self.state = CHOOSE_PREFERENCES_TASK_STATE.UNKNOWN_EQUIPMENT_SLOT
                    return POSTPONED_TASK_LOGIC_RESULT.ERROR

            hero.preferences.equipment_slot = equipment_slot
            hero.preferences.equipment_slot_changed_at = datetime.datetime.now()

        else:
            main_task.comment = u'unknown preference type: %s' % (self.preference_type, )
            self.state = CHOOSE_PREFERENCES_TASK_STATE.UNKNOWN_PREFERENCE
            return POSTPONED_TASK_LOGIC_RESULT.ERROR

        with nested_commit_on_success():
            storage.save_hero_data(hero.id)

        self.state = CHOOSE_PREFERENCES_TASK_STATE.PROCESSED

        return POSTPONED_TASK_LOGIC_RESULT.SUCCESS