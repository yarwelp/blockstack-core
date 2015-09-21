# -*- coding: utf-8 -*-
"""
    Resolver
    ~~~~~

    copyright: (c) 2014 by Halfmoon Labs, Inc.
    copyright: (c) 2015 by Blockstack.org

This file is part of Resolver.

    Resolver is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Resolver is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Resolver. If not, see <http://www.gnu.org/licenses/>.
"""

import json
import re
import pylibmc

from flask import Flask, make_response, jsonify, abort, request
from time import time
from basicrpc import Proxy

from .proofcheck import profile_to_proofs
from .crossdomain import crossdomain

from .config import DEBUG
from .config import DEFAULT_HOST, MEMCACHED_SERVERS, MEMCACHED_USERNAME
from .config import MEMCACHED_PASSWORD, MEMCACHED_TIMEOUT, MEMCACHED_ENABLED
from .config import USERSTATS_TIMEOUT
from .config import VALID_BLOCKS, RECENT_BLOCKS
from .config import BLOCKSTORED_SERVER, BLOCKSTORED_PORT
from .config import DHT_MIRROR, DHT_MIRROR_PORT

app = Flask(__name__)

mc = pylibmc.Client(MEMCACHED_SERVERS, binary=True,
                    username=MEMCACHED_USERNAME, password=MEMCACHED_PASSWORD,
                    behaviors={"no_block": True,
                               "connect_timeout": 500})


dht_client = Proxy(DHT_MIRROR, DHT_MIRROR_PORT)
blockstore_client = Proxy(BLOCKSTORED_SERVER, BLOCKSTORED_PORT)


def username_is_valid(username):

    regrex = re.compile('^[a-z0-9_]{1,60}$')

    if regrex.match(username):
        return True
    else:
        return False


def refresh_user_count():

    active_users_list = 'xx'  # fetch user info here

    if type(active_users_list) is list:
        mc.set("total_users", str(len(active_users_list)), int(time() + USERSTATS_TIMEOUT))
        mc.set("total_users_old", str(len(active_users_list)), 0)

    return len(active_users_list)


@app.route('/v2/users', methods=['GET'])
@crossdomain(origin='*')
def get_user_count():

    resp = {}
    resp['error'] = "not yet supported"
    return jsonify(resp)

    active_users = []

    if MEMCACHED_ENABLED:

        total_user_count = mc.get("total_users")

        if total_user_count is None:

            total_user_count = mc.get("total_users_old")

            if total_user_count is None:

                total_user_count = refresh_user_count()

            else:

                thread = Thread(target=refresh_user_count)
                thread.start()
    else:

        total_user_count = refresh_user_count()

    info = {}
    stats = {}

    stats['registrations'] = total_user_count
    info['stats'] = stats

    return jsonify(info)


def get_user_profile(username, refresh=False):

    global MEMCACHED_ENABLED

    if refresh:
        MEMCACHED_ENABLED = False

    username = username.lower()

    resp = blockstore_client.lookup(username + ".id")
    resp = resp[0]

    if resp is None:
        abort(404)

    profile_hash = resp['value_hash']

    if MEMCACHED_ENABLED:
        cache_reply = mc.get("profile_" + str(username))
    else:
        cache_reply = None

    if cache_reply is None:

        info = {}

        dht_resp = dht_client.get(profile_hash)
        dht_resp = dht_resp[0]
        profile = json.loads(dht_resp['value'])

        if 'error' in profile:
            info['profile'] = None
            info['error'] = "Malformed profile data"
            info['verifications'] = []
        else:
            info['profile'] = profile
            info['verifications'] = profile_to_proofs(profile, username)

        if MEMCACHED_ENABLED or refresh:
            mc.set("profile_" + str(username), json.dumps(info),
                   int(time() + MEMCACHED_TIMEOUT))
    else:
        info = json.loads(cache_reply)

    return info


@app.route('/v2/users/<usernames>', methods=['GET'])
@crossdomain(origin='*')
def get_users(usernames):

    reply = {}

    if usernames is None:
        reply['error'] = "No usernames given"
        return jsonify(reply)

    if ',' not in usernames:

        username = usernames

        info = get_user_profile(username)
        reply[username] = info

        if 'error' in info:
            return jsonify(reply), 502

        return jsonify(reply), 200

    try:
        usernames = usernames.rsplit(',')
    except:
        reply['error'] = "Invalid input format"
        return jsonify(reply)

    for username in usernames:

        try:
            reply[username] = get_user_profile(username)
        except:
            pass

    return jsonify(reply), 200


@app.route('/v2/namespace')
@crossdomain(origin='*')
def get_namespace():

    resp = {}
    resp['error'] = "not yet supported"
    return jsonify(resp)

    results = {}

    namespace = 'xx'  # get namespace info

    results['usernames'] = namespace['namespace']
    results['profiles'] = namespace['profiles'] 

    return jsonify(results)


@app.route('/')
def index():
    reply = '<hmtl><body>Welcome to this Blockchain ID resolver, see \
            <a href="http://github.com/blockstack/resolver"> \
            this Github repo</a> for details.</body></html>'

    return reply


@app.errorhandler(500)
def internal_error(error):

    reply = []
    return json.dumps(reply)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)
