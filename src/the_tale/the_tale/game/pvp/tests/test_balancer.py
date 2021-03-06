
import smart_imports

smart_imports.all()


class BalancerTestsBase(utils_testcase.TestCase):

    def setUp(self):
        super(BalancerTestsBase, self).setUp()

        self.p1, self.p2, self.p3 = game_logic.create_test_map()

        self.account_1 = self.accounts_factory.create_account()
        self.account_2 = self.accounts_factory.create_account()

        self.hero_1 = heroes_logic.load_hero(account_id=self.account_1.id)
        self.hero_2 = heroes_logic.load_hero(account_id=self.account_2.id)

        amqp_environment.environment.deinitialize()
        amqp_environment.environment.initialize()

        prototypes.Battle1x1Prototype.create(self.account_1)

        self.worker = amqp_environment.environment.workers.pvp_balancer
        self.worker.process_initialize('pvp_balancer')


class BalancerTests(BalancerTestsBase):

    def test_process_initialize(self):
        self.assertTrue(self.worker.initialized)
        self.assertEqual(self.worker.arena_queue, {})
        self.assertEqual(models.Battle1x1.objects.all().count(), 0)

    def test_process_add_to_arena_queue(self):
        battle = self.worker.add_to_arena_queue(self.hero_1.id)
        self.assertEqual(self.worker.add_to_arena_queue(self.hero_1.id), None)
        self.assertEqual(len(self.worker.arena_queue), 1)
        self.assertEqual(list(self.worker.arena_queue.values())[0], pvp_workers_balancer.QueueRecord(account_id=self.account_1.id,
                                                                                                     battle_id=battle.id,
                                                                                                     created_at=battle.created_at,
                                                                                                     hero_level=self.hero_1.level))

    def test_process_add_to_arena_queue_two_requests_from_one_account(self):
        battle_1 = prototypes.Battle1x1Prototype.create(self.account_1)
        battle_2 = prototypes.Battle1x1Prototype.create(self.account_1)
        self.assertEqual(models.Battle1x1.objects.all().count(), 1)
        self.assertEqual(battle_1.id, battle_2.id)

    def test_process_add_to_arena_queue__battle_exists_in_waiting_state(self):
        battle = self.worker.add_to_arena_queue(self.hero_1.id)

        self.worker.arena_queue.clear()

        self.assertEqual(self.worker.add_to_arena_queue(self.hero_1.id).id, battle.id)
        self.assertEqual(len(self.worker.arena_queue), 1)
        self.assertEqual(list(self.worker.arena_queue.values())[0], pvp_workers_balancer.QueueRecord(account_id=self.account_1.id,
                                                                                                     battle_id=battle.id,
                                                                                                     created_at=battle.created_at,
                                                                                                     hero_level=self.hero_1.level))

    def test_process_add_to_arena_queue__battle_exists_not_in_waiting_state(self):
        battle = self.worker.add_to_arena_queue(self.hero_1.id)

        new_state = random.choice([record for record in relations.BATTLE_1X1_STATE.records if not record.is_WAITING])

        battle.state = new_state
        battle.save()

        self.worker.arena_queue.clear()

        self.assertRaises(pvp_workers_balancer.PvPBalancerException, self.worker.add_to_arena_queue, self.hero_1.id)

    def test_process_add_to_arena_queue_second_record(self):
        self.worker.add_to_arena_queue(self.hero_1.id)
        self.worker.add_to_arena_queue(self.hero_2.id)
        self.assertEqual(len(self.worker.arena_queue), 2)

    def test_process_leave_queue_not_waiting_state(self):
        battle_1 = prototypes.Battle1x1Prototype.create(self.account_1)

        battle_1.set_enemy(self.account_2)
        battle_1.save()

        self.assertTrue(prototypes.Battle1x1Prototype.get_by_id(battle_1.id).state.is_PREPAIRING)

        self.worker.leave_arena_queue(self.hero_1.id)

        self.assertTrue(prototypes.Battle1x1Prototype.get_by_id(battle_1.id).state.is_PREPAIRING)

    def test_process_leave_queue_waiting_state(self):
        battle = self.worker.add_to_arena_queue(self.hero_1.id)

        self.assertEqual(len(self.worker.arena_queue), 1)

        self.worker.leave_arena_queue(self.hero_1.id)

        self.assertEqual(len(self.worker.arena_queue), 0)

        self.assertEqual(prototypes.Battle1x1Prototype.get_by_id(battle.id), None)


class BalancerBalancingTests(BalancerTestsBase):

    def setUp(self):

        super(BalancerBalancingTests, self).setUp()

        self.battle_1 = self.worker.add_to_arena_queue(self.hero_1.id)
        self.battle_2 = self.worker.add_to_arena_queue(self.hero_2.id)

        self.test_record_1 = pvp_workers_balancer.QueueRecord(account_id=0, created_at=0, battle_id=0, hero_level=1)
        self.test_record_2 = pvp_workers_balancer.QueueRecord(account_id=1, created_at=1, battle_id=0, hero_level=4)

    def battle_1_record(self, created_at_delta=datetime.timedelta(seconds=0)):
        return pvp_workers_balancer.QueueRecord(account_id=self.account_1.id,
                                                battle_id=self.battle_1.id,
                                                created_at=self.battle_1.created_at + created_at_delta,
                                                hero_level=self.hero_1.level)

    def battle_2_record(self, created_at_delta=datetime.timedelta(seconds=0)):
        return pvp_workers_balancer.QueueRecord(account_id=self.account_2.id,
                                                battle_id=self.battle_2.id,
                                                created_at=self.battle_2.created_at + created_at_delta,
                                                hero_level=self.hero_2.level)

    def test_get_prepaired_queue_empty(self):
        self.worker.leave_arena_queue(self.hero_1.id)
        self.worker.leave_arena_queue(self.hero_2.id)

        records, records_to_bots = self.worker._get_prepaired_queue()
        self.assertEqual(records, [])
        self.assertEqual(records_to_bots, [])

    def test_get_prepaired_queue_one_record(self):
        self.worker.leave_arena_queue(self.hero_2.id)

        records, records_to_bots = self.worker._get_prepaired_queue()
        self.assertEqual(len(records), 1)
        self.assertEqual(records_to_bots, [])

        record = records[0]
        self.assertEqual(record[2], self.battle_1_record())
        self.assertTrue(record[0] <= record[1])

    def test_get_prepaired_queue_one_record_test_time_delta(self):
        # -0.1 since some time will pass from record creatig to real query processing
        battle_1_record = self.battle_1_record(created_at_delta=-datetime.timedelta(seconds=float(conf.settings.BALANCING_TIMEOUT) / conf.settings.BALANCING_MAX_LEVEL_DELTA * 2 - 0.1))
        self.worker.arena_queue[self.account_1.id] = battle_1_record

        self.worker.leave_arena_queue(self.hero_2.id)

        records, records_to_bots = self.worker._get_prepaired_queue()
        self.assertEqual(len(records), 1)
        self.assertEqual(records_to_bots, [])

        record = records[0]
        self.assertEqual(record[2], battle_1_record)
        self.assertEqual(record[0], -5)
        self.assertEqual(record[1], 7)

    def test_get_prepaired_queue_one_record_timeout(self):
        battle_1_record = self.battle_1_record(created_at_delta=-datetime.timedelta(seconds=2))
        self.worker.arena_queue[self.account_1.id] = battle_1_record

        self.worker.leave_arena_queue(self.hero_2.id)

        with mock.patch('the_tale.game.pvp.conf.settings.BALANCING_TIMEOUT', 0):
            records, records_to_bots = self.worker._get_prepaired_queue()

        self.assertEqual(records, [])
        self.assertEqual(len(records_to_bots), 1)

        self.assertEqual(records_to_bots, [battle_1_record])

    def test_get_prepaired_queue_two_records(self):
        records, records_to_bots = self.worker._get_prepaired_queue()

        self.assertEqual(len(records), 2)
        self.assertEqual(records_to_bots, [])

        record_1 = records[0]
        record_2 = records[1]
        self.assertEqual(record_1[2], self.battle_1_record())
        self.assertTrue(record_1[0] <= record_1[1])
        self.assertEqual(record_2[2], self.battle_2_record())
        self.assertTrue(record_2[0] <= record_2[1])

    def test_get_prepaired_queue_two_records_one_timeout(self):
        battle_1_record = self.battle_1_record(created_at_delta=-datetime.timedelta(seconds=2))
        battle_2_record = self.battle_2_record(created_at_delta=-datetime.timedelta(seconds=1))

        self.worker.arena_queue[self.account_1.id] = battle_1_record
        self.worker.arena_queue[self.account_2.id] = battle_2_record

        with mock.patch('the_tale.game.pvp.conf.settings.BALANCING_TIMEOUT', 1.5):
            records, records_to_bots = self.worker._get_prepaired_queue()

        self.assertEqual(len(records), 1)
        self.assertEqual(len(records_to_bots), 1)

        record_2 = records[0]
        self.assertEqual(records_to_bots, [battle_1_record])
        self.assertEqual(record_2[2], battle_2_record)
        self.assertTrue(record_2[0] <= record_2[1])

    def test_search_battles_empty(self):
        battle_pairs, records_to_exclude = self.worker._search_battles([])
        self.assertEqual(battle_pairs, [])
        self.assertEqual(records_to_exclude, [])

    def test_search_battles_one_record(self):
        battle_pairs, records_to_exclude = self.worker._search_battles([(1, 2, 'record_1')])
        self.assertEqual(battle_pairs, [])
        self.assertEqual(records_to_exclude, [])

    def test_has_intersections_false(self):
        record_1 = pvp_workers_balancer.BalancingRecord(min_level=0, max_level=3, record=self.test_record_1)
        record_2 = pvp_workers_balancer.BalancingRecord(min_level=3, max_level=5, record=self.test_record_2)
        self.assertFalse(record_1.has_intersections(record_2))

    def test_has_intersections_true(self):
        record_1 = pvp_workers_balancer.BalancingRecord(min_level=0, max_level=4, record=self.test_record_1)
        record_2 = pvp_workers_balancer.BalancingRecord(min_level=1, max_level=5, record=self.test_record_2)
        self.assertTrue(record_1.has_intersections(record_2))

    def test_search_battles_two_records_unsuitable(self):
        battle_pairs, records_to_exclude = self.worker._search_battles([pvp_workers_balancer.BalancingRecord(min_level=0, max_level=3, record=self.test_record_1),
                                                                        pvp_workers_balancer.BalancingRecord(min_level=3, max_level=5, record=self.test_record_2)])
        self.assertEqual(battle_pairs, [])
        self.assertEqual(records_to_exclude, [])

    def test_search_battles_two_records_suitable(self):
        battle_pairs, records_to_exclude = self.worker._search_battles([pvp_workers_balancer.BalancingRecord(min_level=0, max_level=4, record=self.test_record_1),
                                                                        pvp_workers_balancer.BalancingRecord(min_level=1, max_level=5, record=self.test_record_2)])
        self.assertEqual(battle_pairs, [(self.test_record_1, self.test_record_2)])
        self.assertEqual(records_to_exclude, [self.test_record_1, self.test_record_2])

    def test_clean_queue(self):
        self.worker._clean_queue([], [])
        self.assertEqual(models.Battle1x1.objects.filter(state=relations.BATTLE_1X1_STATE.WAITING).count(), 2)
        self.worker._clean_queue([self.battle_1_record()], [self.battle_2_record()])
        self.assertEqual(self.worker.arena_queue, {})
        self.assertEqual(models.Battle1x1.objects.all().count(), 1)
        self.assertEqual(models.Battle1x1.objects.filter(state=relations.BATTLE_1X1_STATE.WAITING).count(), 1)

    def test_initiate_battle(self):

        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 0)

        self.worker._initiate_battle(self.battle_1_record(), self.battle_2_record(), calculate_ratings=True)

        battle_1 = prototypes.Battle1x1Prototype.get_by_id(self.battle_1.id)
        battle_2 = prototypes.Battle1x1Prototype.get_by_id(self.battle_2.id)

        self.assertEqual(battle_1.enemy_id, self.account_2.id)
        self.assertTrue(battle_1.calculate_rating)
        self.assertEqual(battle_2.enemy_id, self.account_1.id)
        self.assertTrue(battle_2.calculate_rating)

        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 1)

    def test_initiate_battle_without_rating_by_option(self):

        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 0)

        self.worker._initiate_battle(self.battle_1_record(), self.battle_2_record(), calculate_ratings=False)

        battle_1 = prototypes.Battle1x1Prototype.get_by_id(self.battle_1.id)
        battle_2 = prototypes.Battle1x1Prototype.get_by_id(self.battle_2.id)

        self.assertEqual(battle_1.enemy_id, self.account_2.id)
        self.assertFalse(battle_1.calculate_rating)
        self.assertEqual(battle_2.enemy_id, self.account_1.id)
        self.assertFalse(battle_2.calculate_rating)

        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 1)

    def test_initiate_battle_without_rating_by_level(self):

        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 0)

        self.hero_1.level = 100
        heroes_logic.save_hero(self.hero_1)

        self.worker._initiate_battle(self.battle_1_record(), self.battle_2_record())

        battle_1 = prototypes.Battle1x1Prototype.get_by_id(self.battle_1.id)
        battle_2 = prototypes.Battle1x1Prototype.get_by_id(self.battle_2.id)

        self.assertEqual(battle_1.enemy_id, self.account_2.id)
        self.assertFalse(battle_1.calculate_rating)
        self.assertEqual(battle_2.enemy_id, self.account_1.id)
        self.assertFalse(battle_2.calculate_rating)

        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 1)

    def test_initiate_battle_with_bot__no_bots(self):
        records_to_remove, records_to_exclude = self.worker._initiate_battle_with_bot(self.battle_1_record())
        self.assertEqual(records_to_remove, [self.battle_1_record()])
        self.assertEqual(records_to_exclude, [])
        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 0)

    def test_initiate_battle_with_bot__create_battle(self):
        self.hero_1.level = 50
        heroes_logic.save_hero(self.hero_1)

        bot_account = self.accounts_factory.create_account(is_bot=True)

        records_to_remove, records_to_exclude = self.worker._initiate_battle_with_bot(self.battle_1_record())

        bot_battle = prototypes.Battle1x1Prototype.get_by_id(records_to_exclude[1].battle_id)

        bot_record = pvp_workers_balancer.QueueRecord(account_id=bot_account.id,
                                                      battle_id=bot_battle.id,
                                                      created_at=bot_battle.created_at + datetime.timedelta(seconds=0),
                                                      hero_level=1)

        self.assertEqual(records_to_remove, [])
        self.assertEqual(records_to_exclude, [self.battle_1_record(), bot_record])
        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 1)

        battle_player = prototypes.Battle1x1Prototype.get_by_account_id(self.account_1.id)
        battle_bot = prototypes.Battle1x1Prototype.get_by_account_id(bot_account.id)

        self.assertEqual(battle_player.enemy_id, bot_account.id)
        self.assertFalse(battle_player.calculate_rating)
        self.assertEqual(battle_bot.enemy_id, self.account_1.id)
        self.assertFalse(battle_bot.calculate_rating)

    # change tests order to fix sqlite segmentation fault
    def test_1_force_battle(self):

        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 0)
        self.assertEqual(len(self.worker.arena_queue), 2)

        self.worker.force_battle(self.account_1.id, self.account_2.id)

        battle_1 = prototypes.Battle1x1Prototype.get_by_id(self.battle_1.id)
        battle_2 = prototypes.Battle1x1Prototype.get_by_id(self.battle_2.id)

        self.assertEqual(battle_1.enemy_id, self.account_2.id)
        self.assertFalse(battle_1.calculate_rating)
        self.assertEqual(battle_2.enemy_id, self.account_1.id)
        self.assertFalse(battle_2.calculate_rating)

        self.assertEqual(self.worker.arena_queue, {})
        self.assertEqual(game_models.SupervisorTask.objects.all().count(), 1)
