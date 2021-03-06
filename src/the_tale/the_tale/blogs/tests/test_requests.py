
import smart_imports

smart_imports.all()


class BaseTestRequests(utils_testcase.TestCase):

    def setUp(self):
        super(BaseTestRequests, self).setUp()
        self.place1, self.place2, self.place3 = game_logic.create_test_map()
        self.account_1 = self.accounts_factory.create_account()
        self.account_2 = self.accounts_factory.create_account()

        helpers.prepair_forum()

        forum_prototypes.CategoryPrototype.create(caption='category-1', slug=clans_conf.settings.FORUM_CATEGORY_SLUG, order=0)

        self.clan_2 = clans_prototypes.ClanPrototype.create(self.account_2, abbr='abbr2', name='name2', motto='motto', description='description')

    def create_posts(self, number, author, caption_template, text_template):
        return [prototypes.PostPrototype.create(author, caption_template % i, text_template % i) for i in range(number)]

    def check_post_votes(self, post_id, votes):
        post = models.Post.objects.get(id=post_id)
        self.assertEqual(post.votes, votes)

    def check_vote(self, vote, voter, post_id):
        self.assertEqual(vote.voter, voter)
        self.assertEqual(vote._model.post.id, post_id)


class TestIndexRequests(BaseTestRequests):

    def test_no_posts(self):
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:')), texts=(('pgf-no-posts-message', 1),))

    def test_one_page(self):
        self.create_posts(2, self.account_1, 'caption-a1-%d', 'text-a1-%d')
        self.create_posts(3, self.account_2, 'caption-a2-%d', 'text-a2-%d')

        declined_post = prototypes.PostPrototype(models.Post.objects.get(caption='caption-a1-0'))
        declined_post.state = relations.POST_STATE.DECLINED
        declined_post.save()

        texts = [('pgf-no-posts-message', 0),
                 ('caption-a1-0', 0), ('text-a1-0', 0),  # test decline record hidding
                 ('caption-a1-1', 1), ('text-a1-1', 0),
                 ('caption-a2-0', 1), ('text-a2-0', 0),
                 ('caption-a2-1', 1), ('text-a2-1', 0),
                 ('caption-a2-2', 1), ('text-a2-2', 0),
                 (self.account_1.nick, 1),
                 (self.account_2.nick, 3),
                 self.clan_2.abbr]

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:')), texts=texts)

    def create_two_pages(self):
        self.create_posts(conf.settings.POSTS_ON_PAGE, self.account_1, 'caption-a1-%d', 'text-a1-%d')
        self.create_posts(3, self.account_2, 'caption-a2-%d', 'text-a2-%d')

    def test_two_pages(self):
        self.create_two_pages()

        texts = [('pgf-no-posts-message', 0),
                 ('caption-a1-0', 1), ('text-a1-0', 0),
                 ('caption-a1-1', 1), ('text-a1-1', 0),
                 ('caption-a1-2', 1), ('text-a1-2', 0),
                 ('caption-a1-3', 0), ('text-a1-3', 0),
                 ('caption-a2-0', 0), ('text-a2-0', 0),
                 ('caption-a2-2', 0), ('text-a2-2', 0),
                 (self.account_1.nick, 3), (self.account_2.nick, 0),
                 (self.clan_2.abbr, 0)]

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + '?page=2'), texts=texts)

    def test_filter_by_user_no_posts_message(self):
        self.create_two_pages()

        account_4 = self.accounts_factory.create_account()
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + ('?author_id=%d' % account_4.id)),
                           texts=[('pgf-no-posts-message', 1)])

    def test_filter_by_user(self):
        self.create_two_pages()

        account_1_texts = [('pgf-no-posts-message', 0),
                           'caption-a1-0',
                           'caption-a1-1',
                           'caption-a1-2',
                           'caption-a1-3',
                           ('caption-a2-0', 0),
                           ('caption-a2-2', 0),
                           (self.account_1.nick, conf.settings.POSTS_ON_PAGE + 1),  # 1 for filter text
                           (self.account_2.nick, 0)]

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + ('?author_id=%d' % self.account_1.id)),
                           texts=account_1_texts)

        account_2_texts = [('pgf-no-posts-message', 0),
                           ('caption-a1-0', 0),
                           ('caption-a1-1', 0),
                           ('caption-a1-2', 0),
                           ('caption-a1-3', 0),
                           ('caption-a2-0', 1),
                           ('caption-a2-2', 1),
                           (self.account_1.nick, 0),
                           (self.account_2.nick, 3 + 1)]  # 1 for filter text

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + ('?author_id=%d' % self.account_2.id)),
                           texts=account_2_texts)

    def test_order_by(self):
        self.create_two_pages()
        # self.create_posts(blogs_settings.POSTS_ON_PAGE, self.account_1, 'caption-a1-%d', 'text-a1-%d')
        # self.create_posts(1, self.account_2, 'caption-a2-%d', 'text-a2-%d')

        post = prototypes.PostPrototype(models.Post.objects.all().order_by('-created_at')[0])

        # default
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:')), texts=(('caption-a2-2', 1),))
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + '?order_by=created_at'), texts=(('caption-a2-2', 1),))

        # created_at
        post._model.created_at -= datetime.timedelta(seconds=60)
        post.save()

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:')), texts=(('caption-a2-2', 0),))
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + '?order_by=created_at'), texts=(('caption-a2-2', 0),))

        # rating
        post._model.votes = 10
        post.save()

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + '?order_by=created_at'), texts=(('caption-a2-2', 0),))
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + '?order_by=rating'), texts=(('caption-a2-2', 1),))

        # alphabet
        post._model.caption = 'aaaaaaaa-caption'
        post.save()

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + '?order_by=created_at'), texts=(('aaaaaaaa-caption', 0),))
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:') + '?order_by=alphabet'), texts=(('aaaaaaaa-caption', 1),))


class TestNewRequests(BaseTestRequests):

    def setUp(self):
        super(TestNewRequests, self).setUp()
        self.request_login(self.account_1.email)

    def test_unlogined(self):
        self.request_logout()
        url = django_reverse('blogs:posts:new')
        self.check_redirect(url, accounts_logic.login_page_url(url))

    def test_is_fast(self):
        self.account_1.is_fast = True
        self.account_1.save()
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:new')), texts=(('blogs.posts.fast_account', 1),))

    @mock.patch('the_tale.accounts.prototypes.AccountPrototype.is_ban_forum', True)
    def test_banned(self):
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:new')), texts=(('common.ban_forum', 1),))

    def test_success(self):
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:new')))


class TestShowRequests(BaseTestRequests):

    def setUp(self):
        super(TestShowRequests, self).setUp()
        self.create_posts(1, self.account_1, 'caption-a2-%d', 'text-a2-%d')
        self.post = models.Post.objects.all()[0]

    def test_unexsists(self):
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:show', args=[666])), status_code=404)

    def test_show(self):

        texts = [('caption-a2-0', 4),
                 ('text-a2-0', 2),
                 ('pgf-forum-block', 1),
                 ('pgf-add-vote-button', 0),
                 ('pgf-remove-vote-button', 0),
                 (self.clan_2.abbr, 0),
                 (django_reverse('blogs:posts:accept', args=[self.post.id]), 0),
                 (django_reverse('blogs:posts:decline', args=[self.post.id]), 0)]

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:show', args=[self.post.id])), texts=texts)

    def test_show__clan_abbr(self):
        self.create_posts(1, self.account_2, 'caption-a2-%d', 'text-a2-%d')
        post = models.Post.objects.all()[1]

        texts = [self.clan_2.abbr]

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:show', args=[post.id])), texts=texts)

    def test_show_without_vote(self):
        self.request_login(self.account_2.email)
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:show', args=[self.post.id])),
                           texts=[('pgf-add-vote-button', 1),
                                  ('pgf-remove-vote-button', 0)])

    def test_show_with_vote(self):
        self.request_login(self.account_1.email)
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:show', args=[self.post.id])),
                           texts=[('pgf-add-vote-button', 0),
                                  ('pgf-remove-vote-button', 1)])

    def test_show_moderator__not_moderated(self):

        self.request_logout()
        self.request_login(self.account_2.email)
        group = utils_permissions.sync_group('folclor moderation group', ['blogs.moderate_post'])
        group.user_set.add(self.account_2._model)

        self.post.state = relations.POST_STATE.NOT_MODERATED
        self.post.save()

        texts = [(django_reverse('blogs:posts:accept', args=[self.post.id]), 1),
                 (django_reverse('blogs:posts:decline', args=[self.post.id]), 1)]

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:show', args=[self.post.id])), texts=texts)

    def test_show_moderator__accepted(self):

        self.request_logout()
        self.request_login(self.account_2.email)
        group = utils_permissions.sync_group('folclor moderation group', ['blogs.moderate_post'])
        group.user_set.add(self.account_2._model)

        self.post.state = relations.POST_STATE.ACCEPTED
        self.post.save()

        texts = [(django_reverse('blogs:posts:accept', args=[self.post.id]), 0),
                 (django_reverse('blogs:posts:decline', args=[self.post.id]), 1)]

        self.check_html_ok(self.request_html(django_reverse('blogs:posts:show', args=[self.post.id])), texts=texts)

    def test_wrong_state(self):
        self.post.state = relations.POST_STATE.DECLINED
        self.post.save()
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:show', args=[self.post.id])), texts=(('blogs.posts.post_declined', 1),))


class TestCreateRequests(BaseTestRequests):

    def setUp(self):
        super(TestCreateRequests, self).setUp()
        self.request_login(self.account_1.email)

    def get_post_data(self, uids=None):
        data = {'caption': 'post-caption',
                'text': 'post-text-' + '1' * 1000}

        if uids:
            data['meta_objects'] = uids

        return data

    def test_unlogined(self):
        self.request_logout()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data()), 'common.login_required')

    def test_is_fast(self):
        self.account_1.is_fast = True
        self.account_1.save()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data()), 'blogs.posts.fast_account')

    @mock.patch('the_tale.accounts.prototypes.AccountPrototype.is_ban_forum', True)
    def test_banned(self):
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data()), 'common.ban_forum')

    def test_success(self):
        self.assertEqual(forum_models.Thread.objects.all().count(), 0)

        response = self.client.post(django_reverse('blogs:posts:create'), self.get_post_data())

        post = prototypes.PostPrototype(models.Post.objects.all()[0])
        self.assertEqual(post.caption, 'post-caption')
        self.assertEqual(post.text, 'post-text-' + '1' * 1000)
        self.assertEqual(post.votes, 1)
        self.assertTrue(post.state.is_ACCEPTED)

        vote = prototypes.VotePrototype(models.Vote.objects.all()[0])
        self.check_vote(vote, self.account_1, post.id)

        self.check_ajax_ok(response, data={'next_url': django_reverse('blogs:posts:show', args=[post.id])})

        self.assertEqual(forum_models.Thread.objects.all().count(), 1)

    def test_form_errors(self):
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), {}), 'blogs.posts.create.form_errors')

    def test_uids(self):

        post_1, post_2 = self.create_posts(2, self.account_1, 'caption-a1-%d', 'text-a1-%d')

        meta_post_1 = meta_relations.Post.create_from_object(post_1)
        meta_post_2 = meta_relations.Post.create_from_object(post_2)

        with self.check_not_changed(models.Post.objects.count):
            self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data(uids='das')), 'blogs.posts.create.form_errors')
            self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data(uids='das#asas')), 'blogs.posts.create.form_errors')
            self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data(uids='6661#2')), 'blogs.posts.create.form_errors')

            self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data(uids='%s#1' % meta_post_1.uid)), 'blogs.posts.create.form_errors')
            self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data(uids='%s%s' % (meta_post_1.uid, meta_post_2.uid))),
                                  'blogs.posts.create.form_errors')
            self.check_ajax_error(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data(uids='%s%s' % (meta_post_1.uid, meta_post_1.uid))),
                                  'blogs.posts.create.form_errors')

        with self.check_delta(models.Post.objects.count, 1):
            self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:create'), self.get_post_data(uids=' %s %s  ' % (meta_post_1.uid, meta_post_2.uid))))


class TestVoteRequests(BaseTestRequests):

    def setUp(self):
        super(TestVoteRequests, self).setUp()

        self.request_login(self.account_1.email)
        self.client.post(django_reverse('blogs:posts:create'), {'caption': 'post-caption',
                                                                'text': 'post-text-' + '1' * 1000})
        self.post = prototypes.PostPrototype(models.Post.objects.all()[0])

        self.request_logout()
        self.request_login(self.account_2.email)

    def test_unlogined(self):
        self.request_logout()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:vote', args=[self.post.id]), {}), 'common.login_required')

    def test_is_fast(self):
        self.account_2.is_fast = True
        self.account_2.save()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:vote', args=[self.post.id]), {}), 'blogs.posts.fast_account')
        self.check_post_votes(self.post.id, 1)

    def test_post_not_exists(self):
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:vote', args=[666]), {}), 'blogs.posts.post.not_found')

    def test_success_for(self):
        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:vote', args=[self.post.id]), {}))
        vote = prototypes.VotePrototype(models.Vote.objects.all()[1])
        self.check_vote(vote, self.account_2, self.post.id)
        self.check_post_votes(self.post.id, 2)

    def test_already_exists(self):
        prototypes.VotePrototype._db_all().delete()
        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:vote', args=[self.post.id]), {}))
        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:vote', args=[self.post.id]), {}))
        self.check_post_votes(self.post.id, 1)


class TestUnvoteRequests(BaseTestRequests):

    def setUp(self):
        super(TestUnvoteRequests, self).setUp()

        self.request_login(self.account_1.email)
        self.client.post(django_reverse('blogs:posts:create'), {'caption': 'post-caption',
                                                                'text': 'post-text-' + '1' * 1000})
        self.post = prototypes.PostPrototype(models.Post.objects.all()[0])

        self.request_logout()
        self.request_login(self.account_2.email)

    def test_unlogined(self):
        self.request_logout()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:unvote', args=[self.post.id]), {}), 'common.login_required')

    def test_is_fast(self):
        self.account_2.is_fast = True
        self.account_2.save()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:unvote', args=[self.post.id]), {}), 'blogs.posts.fast_account')
        self.check_post_votes(self.post.id, 1)

    def test_post_not_exists(self):
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:unvote', args=[666]), {}), 'blogs.posts.post.not_found')

    def test_remove_unexisted(self):
        prototypes.VotePrototype._db_all().delete()
        self.assertEqual(prototypes.VotePrototype._db_count(), 0)
        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:unvote', args=[self.post.id]), {}))
        self.assertEqual(prototypes.VotePrototype._db_count(), 0)

    def test_remove_existed(self):
        prototypes.VotePrototype._db_all().delete()
        self.assertEqual(prototypes.VotePrototype._db_count(), 0)
        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:vote', args=[self.post.id]), {}))
        self.assertEqual(prototypes.VotePrototype._db_count(), 1)
        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:unvote', args=[self.post.id]), {}))
        self.assertEqual(prototypes.VotePrototype._db_count(), 0)


class TestEditRequests(BaseTestRequests):

    def setUp(self):
        super(TestEditRequests, self).setUp()

        self.request_login(self.account_1.email)

        self.client.post(django_reverse('blogs:posts:create'), {'caption': 'post-X-caption',
                                                                'text': 'post-X-text' + '1' * 1000})
        self.post = prototypes.PostPrototype(models.Post.objects.all()[0])

    def test_unlogined(self):
        self.request_logout()
        url = django_reverse('blogs:posts:edit', args=[self.post.id])
        self.check_redirect(url, accounts_logic.login_page_url(url))

    def test_is_fast(self):
        self.account_1.is_fast = True
        self.account_1.save()
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:edit', args=[self.post.id])), texts=(('blogs.posts.fast_account', 1),))

    @mock.patch('the_tale.accounts.prototypes.AccountPrototype.is_ban_forum', True)
    def test_banned(self):
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:edit', args=[self.post.id])), texts=(('common.ban_forum', 1),))

    def test_unexsists(self):
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:edit', args=[666])), status_code=404)

    def test_no_permissions(self):
        self.request_logout()
        self.request_login(self.account_2.email)
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:edit', args=[self.post.id])), texts=(('blogs.posts.no_edit_rights', 1),))

    def test_moderator(self):
        self.request_logout()
        self.request_login(self.account_2.email)
        group = utils_permissions.sync_group('folclor moderation group', ['blogs.moderate_post'])
        group.user_set.add(self.account_2._model)
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:edit', args=[self.post.id])), texts=(self.post.caption,
                                                                                                              self.post.text))

    def test_wrong_state(self):
        self.post.state = relations.POST_STATE.DECLINED
        self.post.save()
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:edit', args=[self.post.id])), texts=(('blogs.posts.post_declined', 1),))

    def test_success(self):
        self.check_html_ok(self.request_html(django_reverse('blogs:posts:edit', args=[self.post.id])), texts=(self.post.caption,
                                                                                                              self.post.text))


class TestUpdateRequests(BaseTestRequests):

    def setUp(self):
        super(TestUpdateRequests, self).setUp()
        self.request_login(self.account_1.email)
        self.client.post(django_reverse('blogs:posts:create'), {'caption': 'post-X-caption',
                                                                'text': 'post-X-text-' + '1' * 1000})
        self.post = prototypes.PostPrototype(models.Post.objects.all()[0])

    def get_post_data(self, uids=None):
        data = {'caption': 'new-X-caption',
                'text': 'new-X-text-' + '1' * 1000}

        if uids:
            data['meta_objects'] = uids

        return data

    def test_unlogined(self):
        self.request_logout()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data()), 'common.login_required')

    def test_is_fast(self):
        self.account_1.is_fast = True
        self.account_1.save()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data()), 'blogs.posts.fast_account')

    @mock.patch('the_tale.accounts.prototypes.AccountPrototype.is_ban_forum', True)
    def test_banned(self):
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data()), 'common.ban_forum')

    def test_no_permissions(self):
        self.request_logout()
        self.request_login(self.account_2.email)
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data()), 'blogs.posts.no_edit_rights')

    def test_moderator(self):
        self.request_logout()
        self.request_login(self.account_2.email)
        group = utils_permissions.sync_group('folclor moderation group', ['blogs.moderate_post'])
        group.user_set.add(self.account_2._model)
        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data()))

    def test_wrong_state(self):
        self.post.state = relations.POST_STATE.DECLINED
        self.post.save()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data()), 'blogs.posts.post_declined')

    def test_form_errors(self):
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), {}), 'blogs.posts.update.form_errors')

    def test_update_success(self):
        old_updated_at = self.post.updated_at

        self.assertEqual(models.Post.objects.all().count(), 1)

        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data()))

        self.post = prototypes.PostPrototype.get_by_id(self.post.id)
        self.assertTrue(old_updated_at < self.post.updated_at)

        self.assertEqual(self.post.caption, 'new-X-caption')
        self.assertEqual(self.post.text, 'new-X-text-' + '1' * 1000)

        self.assertTrue(self.post.state.is_ACCEPTED)

        self.assertEqual(models.Post.objects.all().count(), 1)
        self.assertEqual(forum_models.Thread.objects.all()[0].caption, 'new-X-caption')

    def test_update__uids(self):

        meta_post = meta_relations.Post.create_from_object(self.post)

        post_1, post_2, post_3 = self.create_posts(3, self.account_1, 'caption-a1-%d', 'text-a1-%d')

        meta_post_1 = meta_relations.Post.create_from_object(post_1)
        meta_post_2 = meta_relations.Post.create_from_object(post_2)
        meta_post_3 = meta_relations.Post.create_from_object(post_3)

        with self.check_delta(dext_meta_relations_models.Relation.objects.count, 2):
            self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data(uids='%s %s' % (meta_post_2.uid, meta_post_3.uid))))

        self.assertFalse(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_1))
        self.assertTrue(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_2))
        self.assertTrue(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_3))

        with self.check_delta(dext_meta_relations_models.Relation.objects.count, -1):
            self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data(uids=meta_post_1.uid)))

        self.assertTrue(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_1))
        self.assertFalse(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_2))
        self.assertFalse(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_3))

        with self.check_delta(dext_meta_relations_models.Relation.objects.count, 0):
            self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:update', args=[self.post.id]), self.get_post_data(uids=meta_post_3.uid)))

        self.assertFalse(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_1))
        self.assertFalse(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_2))
        self.assertTrue(dext_meta_relations_logic.is_relation_exists(meta_relations.IsAbout, meta_post, meta_post_3))


class TestModerateRequests(BaseTestRequests):

    def setUp(self):
        super(TestModerateRequests, self).setUp()

        self.request_login(self.account_1.email)

        self.client.post(django_reverse('blogs:posts:create'), {'caption': 'post-caption',
                                                                'text': 'post-text-' + '1' * 1000})
        self.post = prototypes.PostPrototype(models.Post.objects.all()[0])

        self.request_logout()
        self.request_login(self.account_2.email)

        group = utils_permissions.sync_group('folclor moderation group', ['blogs.moderate_post'])
        group.user_set.add(self.account_2._model)

    def test_unlogined(self):
        self.request_logout()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:accept', args=[self.post.id]), {}), 'common.login_required')
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:decline', args=[self.post.id]), {}), 'common.login_required')

    def test_is_fast(self):
        self.account_2.is_fast = True
        self.account_2.save()
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:accept', args=[self.post.id]), {}), 'blogs.posts.fast_account')
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:decline', args=[self.post.id]), {}), 'blogs.posts.fast_account')

    def test_type_not_exist(self):
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:accept', args=[666]), {}), 'blogs.posts.post.not_found')
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:decline', args=[666]), {}), 'blogs.posts.post.not_found')

    def test_no_permissions(self):
        self.request_logout()
        self.request_login(self.account_1.email)
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:accept', args=[self.post.id]), {}), 'blogs.posts.moderator_rights_required')
        self.check_ajax_error(self.client.post(django_reverse('blogs:posts:decline', args=[self.post.id]), {}), 'blogs.posts.moderator_rights_required')

    def test_delete_success(self):
        self.assertEqual(forum_prototypes.PostPrototype._db_count(), 1)

        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:accept', args=[self.post.id]), {}))
        self.assertTrue(prototypes.PostPrototype.get_by_id(self.post.id).state.is_ACCEPTED)

        self.check_ajax_ok(self.client.post(django_reverse('blogs:posts:decline', args=[self.post.id]), {}))
        self.assertTrue(prototypes.PostPrototype.get_by_id(self.post.id).state.is_DECLINED)

        self.assertEqual(forum_prototypes.PostPrototype._db_count(), 2)
