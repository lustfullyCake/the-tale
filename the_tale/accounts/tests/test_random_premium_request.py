# coding: utf-8

import datetime

from the_tale.common.utils import testcase

from the_tale.game.logic import create_test_map

from the_tale.accounts.personal_messages.prototypes import MessagePrototype

from the_tale.accounts.logic import get_system_user
from the_tale.accounts.prototypes import AccountPrototype, RandomPremiumRequestPrototype
from the_tale.accounts import relations
from the_tale.accounts.conf import accounts_settings



class RandomPremiumRequestPrototypeTests(testcase.TestCase):

    def setUp(self):
        super(RandomPremiumRequestPrototypeTests, self).setUp()

        create_test_map()

        self.account_1 = self.accounts_factory.create_account()
        self.account_2 = self.accounts_factory.create_account()

        AccountPrototype._db_all().update(created_at=datetime.datetime.now() - accounts_settings.RANDOM_PREMIUM_CREATED_AT_BARRIER)

        self.request = RandomPremiumRequestPrototype.create(self.account_1.id, days=30)

    def test_create(self):
        self.assertEqual(RandomPremiumRequestPrototype._db_count(), 1)
        self.assertEqual(self.request.days, 30)
        self.assertEqual(self.request.initiator_id, self.account_1.id)

    def test_get_unprocessed__not_exist(self):
        RandomPremiumRequestPrototype._db_all().delete()
        self.assertEqual(RandomPremiumRequestPrototype.get_unprocessed(), None)

    def test_get_unprocessed__no_waiting(self):
        RandomPremiumRequestPrototype._db_all().update(state=relations.RANDOM_PREMIUM_REQUEST_STATE.PROCESSED)
        self.assertEqual(RandomPremiumRequestPrototype.get_unprocessed(), None)

    def test_get_unprocessed__has_waiting(self):
        self.assertEqual(RandomPremiumRequestPrototype.get_unprocessed().id, self.request.id)

    def check_not_processed(self, premiums=0):
        self.assertEqual(MessagePrototype._db_count(), 0)
        self.assertEqual(AccountPrototype._db_filter(premium_end_at__gt=datetime.datetime.now()).count(), premiums)

        self.request.reload()
        self.assertTrue(self.request.state.is_WAITING)
        self.assertEqual(self.request.receiver_id, None)

    def test_process__no_active_accounts(self):
        AccountPrototype._db_all().update(active_end_at=datetime.datetime.now())
        self.request.process()
        self.check_not_processed()

    def test_process__only_fast_accounts(self):
        AccountPrototype._db_all().update(active_end_at=datetime.datetime.now() + datetime.timedelta(days=1), is_fast=True)
        self.request.process()
        self.check_not_processed()

    def test_process__only_premium_accounts(self):
        AccountPrototype._db_all().update(active_end_at=datetime.datetime.now() + datetime.timedelta(days=1),
                                          premium_end_at=datetime.datetime.now() + datetime.timedelta(days=1))
        self.request.process()
        self.check_not_processed(premiums=2)

    def test_process__only_active_initiator(self):
        AccountPrototype._db_all().update(active_end_at=datetime.datetime.now() + datetime.timedelta(days=1))
        self.account_2.remove()
        self.request.process()
        self.check_not_processed()

    def test_process__has_active_accounts(self):
        AccountPrototype._db_all().update(active_end_at=datetime.datetime.now() + datetime.timedelta(days=1))

        self.request.process()

        self.assertEqual(MessagePrototype._db_count(), 1)

        message = MessagePrototype._db_get_object(0)
        self.assertEqual(message.recipient_id, self.account_2.id)
        self.assertEqual(message.sender_id, get_system_user().id)

        self.assertEqual(list(AccountPrototype._db_filter(premium_end_at__gt=datetime.datetime.now()).values_list('id', flat=True)), [self.account_2.id])

        self.request.reload()
        self.assertTrue(self.request.state.is_PROCESSED)
        self.assertEqual(self.request.receiver_id, self.account_2.id)


    def test_process__has_only_new_active_accounts(self):
        AccountPrototype._db_all().update(active_end_at=datetime.datetime.now() + datetime.timedelta(days=1),
                                          created_at=datetime.datetime.now())

        self.request.process()
        self.check_not_processed()
