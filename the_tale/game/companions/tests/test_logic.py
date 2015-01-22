# coding: utf-8
import mock

from the_tale.common.utils import testcase

from the_tale.linguistics import relations as linguistics_relations

from the_tale.game import names

from the_tale.game.companions import logic
from the_tale.game.companions import models
from the_tale.game.companions import storage
from the_tale.game.companions import objects
from the_tale.game.companions import relations



class LogicTests(testcase.TestCase):

    def setUp(self):
        super(LogicTests, self).setUp()


    def test_create_companion_record(self):
        name = names.generator.get_test_name()
        description = u'test description'

        type = relations.TYPE.random()
        dedication = relations.DEDICATION.random()
        rarity = relations.RARITY.random()
        max_health = 10

        with self.check_delta(models.CompanionRecord.objects.count, 1):
            with self.check_changed(lambda: storage.companions._version):
                with self.check_delta(storage.companions.__len__, 1):
                    companion_record = logic.create_companion_record(utg_name=name,
                                                                     description=description,
                                                                     type=type,
                                                                     max_health=max_health,
                                                                     dedication=dedication,
                                                                     rarity=rarity)

        self.assertTrue(companion_record.state.is_DISABLED)

        self.assertEqual(companion_record.name, name.normal_form())
        self.assertEqual(companion_record.utg_name, name)
        self.assertEqual(companion_record.description, description)
        self.assertEqual(companion_record.type, type)
        self.assertEqual(companion_record.max_health, max_health)
        self.assertEqual(companion_record.rarity, rarity)
        self.assertEqual(companion_record.dedication, dedication)

        model = models.CompanionRecord.objects.get(id=companion_record.id)

        loaded_companion = objects.CompanionRecord.from_model(model)

        self.assertEqual(loaded_companion, companion_record)


    def test_create_companion_record__set_state(self):
        companion_record = logic.create_companion_record(utg_name=names.generator.get_test_name(),
                                                         description='description',
                                                         type=relations.TYPE.random(),
                                                         max_health=10,
                                                         dedication=relations.DEDICATION.random(),
                                                         rarity=relations.RARITY.random(),
                                                         state=relations.STATE.ENABLED)

        self.assertTrue(companion_record.state.is_ENABLED)


    def test_create_companion_record__linguistics_restriction_setupped(self):
        with mock.patch('the_tale.linguistics.logic.sync_restriction') as sync_restriction:
            companion_record = logic.create_companion_record(utg_name=names.generator.get_test_name(),
                                                            description='description',
                                                            type=relations.TYPE.random(),
                                                            max_health=10,
                                                            dedication=relations.DEDICATION.random(),
                                                            rarity=relations.RARITY.random(),
                                                            state=relations.STATE.ENABLED)

        self.assertEqual(sync_restriction.call_args_list, [mock.call(group=linguistics_relations.TEMPLATE_RESTRICTION_GROUP.COMPANION,
                                                                     external_id=companion_record.id,
                                                                     name=companion_record.name)])


    def test_update_companion_record(self):
        old_name = names.generator.get_test_name(name='old')
        new_name = names.generator.get_test_name(name='new')

        type = relations.TYPE.random()
        dedication = relations.DEDICATION.random()
        rarity = relations.RARITY.random()
        max_health = 666

        companion_record = logic.create_companion_record(utg_name=old_name,
                                                         description='old-description',
                                                         type=relations.TYPE.random(),
                                                         max_health=10,
                                                         dedication=relations.DEDICATION.random(),
                                                         rarity=relations.RARITY.random())

        with self.check_increased(lambda: models.CompanionRecord.objects.get(id=companion_record.id).updated_at):
            with self.check_not_changed(lambda: models.CompanionRecord.objects.get(id=companion_record.id).created_at):
                with self.check_not_changed(models.CompanionRecord.objects.count):
                    with self.check_changed(lambda: storage.companions._version):
                        with self.check_not_changed(storage.companions.__len__):
                            logic.update_companion_record(companion_record,
                                                          utg_name=new_name,
                                                          description='new-description',
                                                          type=type,
                                                          max_health=max_health,
                                                          dedication=dedication,
                                                          rarity=rarity)

        self.assertEqual(companion_record.name, new_name.normal_form())
        self.assertEqual(companion_record.description, 'new-description')
        self.assertEqual(companion_record.type, type)
        self.assertEqual(companion_record.dedication, dedication)
        self.assertEqual(companion_record.max_health, max_health)
        self.assertEqual(companion_record.rarity, rarity)

        storage.companions.refresh()

        companion_record = storage.companions[companion_record.id]

        self.assertEqual(companion_record.name, new_name.normal_form())
        self.assertEqual(companion_record.description, 'new-description')
        self.assertEqual(companion_record.type, type)
        self.assertEqual(companion_record.dedication, dedication)
        self.assertEqual(companion_record.max_health, max_health)
        self.assertEqual(companion_record.rarity, rarity)


    def test_enable_companion_record(self):

        type = relations.TYPE.random()
        dedication = relations.DEDICATION.random()
        rarity = relations.RARITY.random()
        max_health = 666

        companion_record = logic.create_companion_record(utg_name=names.generator.get_test_name(name='old'),
                                                         description='old-description',
                                                         type=type,
                                                         max_health=max_health,
                                                         dedication=dedication,
                                                         rarity=rarity)

        with self.check_increased(lambda: models.CompanionRecord.objects.get(id=companion_record.id).updated_at):
            with self.check_not_changed(lambda: models.CompanionRecord.objects.get(id=companion_record.id).created_at):
                with self.check_not_changed(models.CompanionRecord.objects.count):
                    with self.check_changed(lambda: storage.companions._version):
                        with self.check_not_changed(storage.companions.__len__):
                            logic.enable_companion_record(companion_record)

        self.assertEqual(companion_record.description, 'old-description')
        self.assertEqual(companion_record.type, type)
        self.assertEqual(companion_record.dedication, dedication)
        self.assertEqual(companion_record.max_health, max_health)
        self.assertEqual(companion_record.rarity, rarity)
        self.assertTrue(companion_record.state.is_ENABLED)

        storage.companions.refresh()

        companion_record = storage.companions[companion_record.id]

        self.assertEqual(companion_record.description, 'old-description')
        self.assertEqual(companion_record.type, type)
        self.assertEqual(companion_record.dedication, dedication)
        self.assertEqual(companion_record.max_health, max_health)
        self.assertEqual(companion_record.rarity, rarity)
        self.assertTrue(companion_record.state.is_ENABLED)


    def test_update_companion_record__linguistics_restrictions(self):
        old_name = names.generator.get_test_name(name='old')
        new_name = names.generator.get_test_name(name='new')

        companion_record = logic.create_companion_record(utg_name=old_name,
                                                         description='old-description',
                                                         type=relations.TYPE.random(),
                                                         max_health=10,
                                                         dedication=relations.DEDICATION.random(),
                                                         rarity=relations.RARITY.random())

        with mock.patch('the_tale.linguistics.logic.sync_restriction') as sync_restriction:
            logic.update_companion_record(companion_record,
                                          utg_name=new_name,
                                          description='new-description',
                                          type=relations.TYPE.random(),
                                          max_health=10,
                                          dedication=relations.DEDICATION.random(),
                                          rarity=relations.RARITY.random())

        self.assertEqual(sync_restriction.call_args_list, [mock.call(group=linguistics_relations.TEMPLATE_RESTRICTION_GROUP.COMPANION,
                                                                     external_id=companion_record.id,
                                                                     name=new_name.normal_form())])

    def test_create_companion(self):
        companion_record = logic.create_companion_record(utg_name=names.generator.get_test_name(),
                                                         description='description',
                                                         type=relations.TYPE.random(),
                                                         max_health=10,
                                                         dedication=relations.DEDICATION.random(),
                                                         rarity=relations.RARITY.random(),
                                                         state=relations.STATE.ENABLED)

        companion = logic.create_companion(companion_record)

        self.assertEqual(companion.record.id, companion_record.id)
        self.assertEqual(companion.health, companion_record.max_health)
        self.assertEqual(companion.coherence, 0)
