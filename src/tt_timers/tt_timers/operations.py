
import asyncio
import logging
import datetime

import aiohttp

import psycopg2
from psycopg2.extras import Json as PGJson

from tt_protocol.protocol import timers_pb2

from tt_web import postgresql as db
from tt_web.common import unique_priority_queue

from . import objects
from . import protobuf
from . import relations
from . import exceptions


TIMERS_QUEUE = unique_priority_queue.Queue()


def timer_from_row(row):
    return objects.Timer(id=row['id'],
                         owner_id=row['owner'],
                         entity_id=row['entity'],
                         type=row['type'],
                         speed=row['speed'],
                         border=row['border'],
                         resources=row['resources'],
                         resources_at=row['resources_at'].replace(tzinfo=None),
                         finish_at=row['finish_at'].replace(tzinfo=None))


async def create_timer(owner_id, entity_id, type, speed, border, callback_data, resources):
    sql = '''INSERT INTO timers (owner, entity, type, speed, resources, border, restarted, resources_at, finish_at, data, created_at, updated_at)
             VALUES (%(owner_id)s, %(entity_id)s, %(type)s, %(speed)s, %(resources)s, %(border)s, 0, NOW(), NOW() + %(delay)s, %(data)s, NOW(), NOW())
             RETURNING *'''

    try:
        results = await db.sql(sql, {'owner_id': owner_id,
                                     'entity_id': entity_id,
                                     'type': type,
                                     'speed': speed,
                                     'resources': resources,
                                     'border': border,
                                     'delay': datetime.timedelta(seconds=(border-resources)/speed),
                                     'data': PGJson({'callback_data': callback_data})})
    except psycopg2.IntegrityError:
        logging.warning('timer for owner: %s, entity: %s, type: %s already exists', owner_id, entity_id, type)
        raise exceptions.TimerAlreadyExists(owner_id=owner_id,
                                            entity_id=entity_id,
                                            type=type)

    timer = timer_from_row(results[0])

    TIMERS_QUEUE.push(timer.id, timer.finish_at)

    logging.info('timer %s created, owner: %s, entity: %s, type: %s, speed: %s, border: %s, resources: %s, finish_at: %s',
                 timer.id, timer.owner_id, timer.entity_id, timer.type, timer.speed, timer.border, timer.resources, timer.finish_at)

    return timer


async def change_speed(owner_id, entity_id, type, speed):
    results = await db.sql('''UPDATE timers
                              SET speed=%(speed)s,
                                  resources=resources+extract('epoch' from (NOW()-resources_at))*speed,
                                  resources_at=NOW(),
                                  finish_at=NOW() + ((border - (resources+extract('epoch' from (NOW()-resources_at))*speed)) / %(speed)s) * INTERVAL '1 SECOND',
                                  updated_at=NOW()
                              WHERE owner=%(owner_id)s AND entity=%(entity_id)s AND type=%(type)s
                              RETURNING *''',
                           {'owner_id': owner_id,
                            'entity_id': entity_id,
                            'type': type,
                            'speed': speed})

    if not results:
        raise exceptions.TimerNotFound(owner_id=owner_id, entity_id=entity_id, type=type)

    timer = timer_from_row(results[0])

    TIMERS_QUEUE.push(timer.id, timer.finish_at)

    logging.info('timer %s updated, owner: %s, entity: %s, type: %s, speed: %s, border: %s, resources: %s, finish_at: %s',
                 timer.id, timer.owner_id, timer.entity_id, timer.type, timer.speed, timer.border, timer.resources, timer.finish_at)

    return timer


async def load_all_timers():
    logging.info('load all timers')

    results = await db.sql('SELECT id, finish_at FROM timers')

    logging.info('timers found: %s', len(results))

    for row in results:
        logging.info('load timer %s', row['id'])
        TIMERS_QUEUE.push(row['id'], row['finish_at'].replace(tzinfo=None))

    logging.info('all timers loaded')


def finish_completed_timers(scheduler, config):
    now = datetime.datetime.utcnow()

    while not TIMERS_QUEUE.empty():
        timer_id, finish_at = TIMERS_QUEUE.first()

        if timer_id is None:
            break

        if now < finish_at:
            break

        TIMERS_QUEUE.pop()

        logging.info('initiate timer %s finish', timer_id)

        scheduler(finish_timer, timer_id, config)


async def make_callback(secret, url, timer, data):
    logging.info('initialize callback with owner: %s, entity: %s, type: %s to %s',
                 timer.owner_id, timer.entity_id, timer.type, url)

    async with aiohttp.ClientSession() as session:
        data = timers_pb2.CallbackBody(timer=protobuf.from_timer(timer),
                                       secret=secret,
                                       callback_data=data)
        async with session.post(url, data=data.SerializeToString()) as response:
            return response.status == 200


async def postprocess_timer(timer_id, type):
    if type.upper() == relations.POSTPROCESS_TYPE.RESTART.name:
        return await postprocess_restart(timer_id)

    raise NotImplementedError


async def finish_timer(timer_id, config, callback=make_callback, postprocess=postprocess_timer):
    while True:
        logging.info('try to finish timer %s', timer_id)

        results = await db.sql('SELECT * FROM timers WHERE id=%(id)s', {'id': timer_id})

        if not results:
            return

        timer = timer_from_row(results[0])

        if datetime.datetime.utcnow() <= timer.finish_at:
            logging.info('timer %s finish time changed, do nothing', timer_id)
            # do not add back to TIMERS_QUEUE, since new values should already be there
            return

        type = str(results[0]['type'])

        if type not in config['types']:
            raise exceptions.WrongTimerType(type=type, timer_id=timer_id)

        type_info = config['types'][type]

        result = await callback(secret=config['secret'],
                                url=type_info['url'],
                                timer=timer,
                                data=results[0]['data']['callback_data'])

        if not result:
            logging.info('timer %s callback failed, another try after %s seconds', timer_id, config['delay_before_callback_retry'])
            await asyncio.sleep(config['delay_before_callback_retry'])
            continue

        logging.info('timer %s callback successed', timer_id)

        await postprocess(timer_id=timer_id, type=type_info['postprocess_type'])
        return


async def postprocess_restart(timer_id):
    logging.info('restart timer %s', timer_id)

    results = await db.sql('''UPDATE timers
                              SET resources=0,
                                  resources_at=finish_at,
                                  finish_at=finish_at + (border / speed) * INTERVAL '1 SECOND',
                                  restarted=restarted+1,
                                  updated_at=NOW()
                              WHERE id=%(id)s
                              RETURNING finish_at''', {'id': timer_id})

    TIMERS_QUEUE.push(timer_id, results[0]['finish_at'].replace(tzinfo=None))


async def get_owner_timers(owner_id):
    results = await db.sql('SELECT * FROM timers WHERE owner=%(owner_id)s', {'owner_id': owner_id})

    timers = [timer_from_row(row) for row in results]

    timers.sort(key=lambda timer: timer.finish_at)

    return timers


async def clean_database():
    await db.sql('DELETE FROM timers')

    TIMERS_QUEUE.clean()
