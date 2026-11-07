# -*- coding: utf-8 -*-
# ExportShipStatus core: battle lifecycle, 1 Hz health snapshots, 0.25 s
# burning/flooding polling, JSON Lines output via the file bridge.
#
# Runs inside the WOWS PnFMods sandbox (Python 2 semantics, no sockets,
# file output is documented and proven by Aslain mods). This file stays
# py2-compatible and py3-parseable: no f-strings, `as` exception syntax.

try:
    import battle, events, callbacks, utils, dataHub, constants
except Exception:
    pass

import time

CC = constants.UiComponents
RELATION_SELF = constants.PlayerRelation.SELF

LOG_INTERVAL_SEC = 10.0            # error-log rate limit
OUTPUT_NAME = 'wows_telemetry.jsonl'

try:
    _INT_TYPES = (int, long, float)   # py2 sandbox
except NameError:
    _INT_TYPES = (int, float)         # py3 (offline tests)


class TelemetryCore(object):

    def __init__(self, logInfo, logError):
        self._log = logInfo
        self._logError = logError
        self._seq = 0
        self._file = None
        self._path = None
        self._inBattle = False
        self._ship = None
        self._shipId = None
        self._avatarId = None          # avatar id (the space State.ownerId lives in)
        self._snapshotCb = None
        self._statusCb = None
        self._prevStatus = None
        self._nextLogTime = 0.0
        self._snapIssueLogged = False        # one-shot-per-battle notes (reset in
        self._snapWrittenLogged = False      # on_battle_shown, so they must exist
        self._statusDebugLogged = False      # before the first battle starts)
        self._dmgDebugLogged = False
        self._damagesDebugLogged = False
        self._shellDebugLogged = False
        self._debuffAgreeLogged = False      # "boolean vs entity layer" note
        self._shipIdRefreshed = False        # stale-cache self-heal note
        self._stateIdsSeen = ()
        self._stateDumpCount = 0
        try:
            events.onReceiveDamagesOnShip(self._onDamages)
            events.onReceiveShellInfo(self._onShellInfo)
        except Exception as e:
            self._logError('cannot subscribe damage events: {}'.format(e))

    # ------------------------------------------------------------------
    # Lifecycle (subscribed from Main.py)
    # ------------------------------------------------------------------

    def on_battle_shown(self, *args, **kwargs):
        try:
            # A new battle means a new vehicle id: drop the cached ship/id or
            # every id-based check below silently fails for the rest of the
            # session - the damage callbacks reject our own ship (victimId !=
            # stale id) and isVehicleBurning(stale id) is always False, which
            # forces fires/floods to 0 (2026-10-02: "第二局起投掷物不触发、
            # 状态件不显示"; the first battle of a session worked).
            self._ship = None
            self._shipId = None
            self._avatarId = None
            self._ensureShip()
            if self._ship is None:
                self._log('Ship not resolved yet at battle show; will retry')
            if not self._openFile(fresh=True):
                self._logError('Output file unavailable; data will NOT be exported')
            self._inBattle = True
            self._prevStatus = None
            self._snapIssueLogged = False
            self._snapWrittenLogged = False
            self._statusDebugLogged = False
            self._dmgDebugLogged = False
            self._stateIdsSeen = ()
            self._stateDumpCount = 0
            self._damagesDebugLogged = False
            self._shellDebugLogged = False
            self._debuffAgreeLogged = False
            self._shipIdRefreshed = False
            self._writeMessage(self._collectBattleStart())
            self._startTimers()
        except Exception as e:
            self._logError('on_battle_shown failed: {}'.format(e))

    def on_battle_end(self, *args, **kwargs):
        try:
            self._writeMessage({'type': 'battle_end'})
        except Exception as e:
            self._logError('on_battle_end failed: {}'.format(e))
        self._inBattle = False
        self._stopTimers()

    def on_battle_quit(self, *args, **kwargs):
        # Fires when leaving a battle and/or exiting the game.
        try:
            self._inBattle = False
            self._stopTimers()
            self._closeFile()
            self._clearOutput()
        except Exception as e:
            self._logError('on_battle_quit failed: {}'.format(e))

    # ------------------------------------------------------------------
    # Periodic tasks
    # ------------------------------------------------------------------

    def _startTimers(self):
        if self._snapshotCb is not None:
            return
        try:
            self._snapshotCb = callbacks.callback(1.0, self._snapshot)
            self._statusCb = callbacks.callback(0.25, self._pollStatus)
            self._log('Timers started (1s snapshot, 0.25s status)')
        except Exception as e:
            self._logError('cannot start timers: {}'.format(e))
            self._snapshotCb = None
            self._statusCb = None

    def _stopTimers(self):
        for cb in (self._snapshotCb, self._statusCb):
            if cb is not None:
                try:
                    callbacks.cancel(cb)
                except Exception:
                    pass
        self._snapshotCb = None
        self._statusCb = None

    def _snapshot(self, *args, **kwargs):
        if not self._inBattle:
            return
        try:
            self._ensureShip()
            if self._ship is None:
                return  # retry next tick
            # Ship.getHealthData() of the documented battle API returns
            # nothing in the current client. Working pattern (TeamHP mod):
            # read the avatar dataHub entity's health component.
            healthComp = self._findSelfHealthComp()
            if healthComp is None:
                self._logSnapshotIssue('self avatar/health component not found')
                return
            msg = {'type': 'snapshot'}
            maxHealth = self._num(getattr(healthComp, 'max', None))
            rawHealth = self._num(getattr(healthComp, 'value', None))
            alive = _as_bool(getattr(healthComp, 'isAlive', None), True)
            if not alive:
                health = 0
            elif rawHealth <= 0 and maxHealth > 0:
                # Unbound full-bar sentinel: value==0 while alive means the
                # bar has not ticked yet — the ship is at full HP (8111's
                # ui_health.py handles the same case).
                health = maxHealth
            else:
                health = rawHealth
            msg['health'] = health
            msg['max_health'] = maxHealth
            msg['hp_pct'] = self._hpPct(health, maxHealth)
            msg['alive'] = alive
            burning, flooding = self._readDebuffs(alive)
            st = self._read_damage_status(alive, burning, flooding)
            msg['burning'] = burning
            msg['flooding'] = flooding
            msg['fires'] = st.get('fires')
            msg['floods'] = st.get('floods')
            msg['fire_time_left'] = st.get('fire_time_left')
            msg['flood_time_left'] = st.get('flood_time_left')
            if st.get('fire_duration') is not None:
                msg['fire_duration'] = st['fire_duration']
            if st.get('flood_duration') is not None:
                msg['flood_duration'] = st['flood_duration']
            self._writeMessage(msg)
            if not self._snapWrittenLogged:
                self._snapWrittenLogged = True
                self._log('First snapshot written')
        except Exception as e:
            self._logSnapshotIssue(repr(e))

    def _findSelfEntity(self):
        # The avatar dataHub entity whose relation is SELF (FakeEntity:
        # index access only). Returns None when not found.
        try:
            for entity in dataHub.getEntityCollections('avatar'):
                try:
                    if getattr(entity[CC.relation], 'value', None) != RELATION_SELF:
                        continue
                    return entity
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _findSelfHealthComp(self):
        entity = self._findSelfEntity()
        if entity is None:
            return None
        try:
            return entity[CC.health]
        except Exception:
            return None

    def _logSnapshotIssue(self, reason):
        # Report once per battle; repeated silent skips hid the cause before.
        if self._snapIssueLogged:
            return
        self._snapIssueLogged = True
        self._logError('snapshot issue: {}'.format(reason))

    def _pollStatus(self, *args, **kwargs):
        # 0.25s polling is the only way to observe fire/flood start & stop
        # (the API exposes booleans only: no events, no countdown, no count).
        if not self._inBattle:
            return
        self._ensureShip()
        if self._ship is None:
            return
        alive = _as_bool(self._tryCall(self._ship.isAlive), True)
        burning, flooding = self._readDebuffs(alive)
        st = self._read_damage_status(alive, burning, flooding)
        current = {'alive': alive, 'burning': burning, 'flooding': flooding,
                   'fires': st.get('fires'), 'floods': st.get('floods')}
        if self._prevStatus is None:
            # Seed: report pre-existing state, emit no spurious transitions.
            if burning:
                self._writeMessage({'type': 'status_change', 'kind': 'burning', 'state': 'started'})
            if flooding:
                self._writeMessage({'type': 'status_change', 'kind': 'flooding', 'state': 'started'})
        else:
            for kind, cnt in (('burning', 'fires'), ('flooding', 'floods')):
                if current[kind] and not self._prevStatus[kind]:
                    self._writeMessage({'type': 'status_change', 'kind': kind,
                                        'state': 'started', 'count': current[cnt]})
                elif self._prevStatus[kind] and not current[kind]:
                    self._writeMessage({'type': 'status_change', 'kind': kind,
                                        'state': 'ended', 'count': 0})
                elif (self._prevStatus.get(cnt) is not None
                        and current[cnt] is not None
                        and current[cnt] != self._prevStatus.get(cnt)):
                    self._writeMessage({'type': 'count_change', 'kind': kind,
                                        'count': current[cnt]})
            if self._prevStatus['alive'] and not alive:
                self._writeMessage({'type': 'status_change', 'kind': 'alive', 'state': 'ended'})
        self._prevStatus = current

    # ------------------------------------------------------------------
    # Fire / flood stacks and remaining time
    #
    # Derived from the client's own HUD implementation (ModSDK 15.8.0,
    # gui/unbound2/pc/battle/state_panel.unbound), which is the authority on
    # what the battle UI shows above the weapon bar:
    #
    #   statesCollection = $datahub.getCollection(CC.state)
    #   currentCount     = stateEntity.progress.value          <- stack count
    #   remainTime       = stateEntity.countDown.endTime
    #                      - $datahub.getSingleEntity(CC.timer).timer.currentTime
    #   moduleId         = SC.Battle.DAMAGE_MODULES[toUpper(stateComponent.id)]
    #
    # so the state ids are 'burn' / 'flood' (DAMAGE_MODULES.BURN=9,
    # DAMAGE_MODULES.FLOOD=10) and both numbers are exactly the ones drawn on
    # the HUD icon. Note countDown.remain exists but reads 0 on a live fire -
    # the HUD subtracts from endTime, and so do we.
    # ------------------------------------------------------------------

    _STATE_FIRE = ('burn', 'wild_fire')
    _STATE_FLOOD = ('flood',)

    def _cc(self, name):
        for attr in (name, name[:1].lower() + name[1:]):
            try:
                return getattr(CC, attr)
            except Exception:
                pass
        return None

    def _comp(self, entity, key, attr):
        """Read `entity[key].attr`, or None when the component is absent."""
        if key is None:
            return None
        try:
            comp = entity[key]
        except Exception:
            comp = None
        if comp is None:
            return None
        try:
            return getattr(comp, attr, None)
        except Exception:
            return None

    @staticmethod
    def _round(value):
        try:
            return round(float(value), 1)
        except Exception:
            return None

    def _read_states(self):
        """{'burn': {'count','remain','duration'}, ...} from the state collection.

        count    <- progress.value                     (icon badge = stacks)
        remain   <- countDown.endTime - timer.currentTime
        duration <- countDown.duration
        """
        out = {}
        try:
            entities = dataHub.getEntityCollections('state')
        except Exception:
            return out
        kState = self._cc('state')
        kCount = self._cc('countDown')
        kProg = self._cc('progress')
        now = self._game_time()
        sample = []
        for ent in entities or []:
            sid = self._comp(ent, kState, 'id')
            if sid is None:
                continue
            sid = str(sid).strip().lower()
            remain = self._round(self._comp(ent, kCount, 'remain'))
            endTime = self._comp(ent, kCount, 'endTime')
            if endTime is not None and now is not None:
                remain = self._round(endTime - now)
            info = {'count': self._comp(ent, kProg, 'value'),
                    'remain': remain,
                    'owner': self._comp(ent, kState, 'ownerId'),
                    'duration': self._round(self._comp(ent, kCount, 'duration'))}
            # The state collection is NOT owner-filtered and keyed by state id,
            # so another ship's burn can sit on the same key. Keep ours when both
            # exist (2026-10-02: an enemy's burn used to overwrite ours and, once
            # isVehicleBurning was fed a stale id, it was what got reported).
            prev = out.get(sid)
            if prev is None or (self._isMyState(info) and not self._isMyState(prev)):
                out[sid] = info
            if len(sample) < 4:
                sample.append('{}:type={}:count={}:remain={}:dur={}:end={}:owner={}'.format(
                    sid, self._comp(ent, kState, 'type'), info['count'],
                    info['remain'], info['duration'], endTime,
                    self._comp(ent, kState, 'ownerId')))
        ids = tuple(sorted(out.keys()))
        if sample and ids != self._stateIdsSeen and self._stateDumpCount < 12:
            # Dump on every change of the id set (not just once per battle):
            # the first set is usually a perk/consumable state, so a one-shot
            # dump would hide the burn/flood entity that matters. Capped so a
            # flapping set cannot spam the log.
            self._stateIdsSeen = ids
            self._stateDumpCount += 1
            self._log('state entities ({}): {} (now={})'.format(
                len(out), ' | '.join(sample), now))
        return out

    def _game_time(self):
        """Battle clock the HUD itself uses:
        $datahub.getSingleEntity(CC.timer).timer.currentTime  (see state_panel).
        Falls back to utils.getTimeFromGameStart(), else None (never a bogus 0
        - a wrong clock would turn endTime into a nonsense remaining time).
        """
        fn = getattr(dataHub, 'getSingleEntity', None)
        key = self._cc('timer')
        if fn is not None:
            for arg in (key, 'timer'):
                if arg is None:
                    continue
                try:
                    ent = fn(arg)
                except Exception:
                    continue
                if ent is None:
                    continue
                try:
                    return float(ent[arg].currentTime)
                except Exception:
                    try:
                        return float(getattr(getattr(ent, 'timer'), 'currentTime'))
                    except Exception:
                        pass
        try:
            return float(utils.getTimeFromGameStart())
        except Exception:
            return None

    def _read_damage_status(self, alive, burning, flooding):
        status = {'fires': None, 'floods': None,
                  'fire_time_left': None, 'flood_time_left': None,
                  'fire_duration': None, 'flood_duration': None}
        try:
            if not self._inBattle:
                return status
            if not alive:
                status['fires'] = 0
                status['floods'] = 0
                return status
            states = self._read_states()
            mine = {sid: i for sid, i in states.items() if self._isMyState(i)}
            if mine:
                # Only states owned by us count as ours; when no owner is
                # readable the boolean API below is the owner filter instead
                # (the pre-2026-10-02 behaviour).
                states = mine
            for sid in sorted(states.keys()):
                info = states[sid]
                if sid in self._STATE_FIRE:
                    prefix = 'fire'
                elif sid in self._STATE_FLOOD:
                    prefix = 'flood'
                else:
                    continue
                if info['count'] is not None:
                    status[prefix + 's'] = self._num(info['count'])
                if info['remain'] is not None:
                    status[prefix + '_time_left'] = info['remain']
                if info['duration'] is not None:
                    status[prefix + '_duration'] = info['duration']
            # The state collection is not owner-filtered, while
            # isVehicleBurning/Flooding know about our ship only - so they are
            # what keeps another ship's state entity out of our numbers, and
            # they also give a definite 0 (instead of null) when nothing burns.
            # But when the two DISAGREE in our favour, believe the entity layer:
            # it carries our owner id, and a stale ship id made the boolean say
            # False forever (fires stuck at 0 while we burned, 2026-10-02).
            if mine:
                if not burning and any(s in self._STATE_FIRE for s in mine):
                    burning = True
                    self._noteDebuffDisagreement('burn')
                if not flooding and any(s in self._STATE_FLOOD for s in mine):
                    flooding = True
                    self._noteDebuffDisagreement('flood')
            if not burning:
                status['fires'] = 0
                status['fire_time_left'] = None
                status['fire_duration'] = None
            if not flooding:
                status['floods'] = 0
                status['flood_time_left'] = None
                status['flood_duration'] = None
            if not self._dmgDebugLogged and (states or burning or flooding):
                # First meaningful moment of the battle (a fire/flood exists or
                # one of them is flagged): dump what was derived from the state
                # entities, and report a miss when the boolean and the entity
                # layer disagree.
                self._dmgDebugLogged = True
                self._log('dmg status: fires={} floods={} fire_left={} flood_left={} '
                          'states={}'.format(status['fires'], status['floods'],
                                             status['fire_time_left'],
                                             status['flood_time_left'],
                                             self._format_states(states)))
                if burning and status['fires'] is None:
                    self._logError('burning but no burn state entity '
                                   '(ids seen: {})'.format(sorted(states.keys())))
                if flooding and status['floods'] is None:
                    self._logError('flooding but no flood state entity '
                                   '(ids seen: {})'.format(sorted(states.keys())))
        except Exception as e:
            if not self._dmgDebugLogged:
                self._dmgDebugLogged = True
                self._logError('dmg status read failed: {}'.format(e))
        return status

    @staticmethod
    def _format_states(states):
        parts = []
        for sid in sorted(states.keys()):
            info = states[sid]
            parts.append('{}:n={}:left={}:dur={}'.format(
                sid, info['count'], info['remain'], info['duration']))
        return ','.join(parts)

    def _noteDebuffDisagreement(self, kind):
        """Log once per battle: the boolean API said no, the entity said yes."""
        if self._debuffAgreeLogged:
            return
        self._debuffAgreeLogged = True
        self._log('isVehicle{}={} but a {} entity is owned by us - trusting the '
                  'entity layer'.format('Flooding' if kind == 'flood' else 'Burning',
                                        'False', kind))

    def _selfAvatarId(self):
        """Our AVATAR/account id - what `State.ownerId` actually holds.

        State entities belong to the avatar entity, not the vehicle, so this is
        NOT `getSelfPlayerShip()._Ship__id` (SPEC §2.C measured both: 24383 vs
        785139). DamageMonitor resolves it the same way.
        """
        if self._avatarId is not None:
            return self._avatarId
        if self._shipId is None:
            return None
        try:
            info = battle.getPlayerByVehicleId(self._shipId)
            if info is not None:
                self._avatarId = getattr(info, 'id', None)
        except Exception:
            pass
        return self._avatarId

    def _isMyState(self, info):
        """Does this state entity belong to our ship? (compare AVATAR ids)

        Used to pick OUR burn/flood out of a collection that mixes every ship's
        states - and, when the boolean API disagrees, to vouch for a burn the
        entity layer clearly attributes to us.
        """
        mine = self._selfAvatarId()
        owner = (info or {}).get('owner')
        if owner is None or mine is None:
            return False
        try:
            return int(owner) == int(mine)
        except Exception:
            return str(owner).strip() == str(mine).strip()

    def _readDebuffs(self, alive):
        if not alive:
            return False, False
        if self._shipId is None:
            # a battle boundary may have cleared the cache; re-resolve once
            self._ensureShip()
        if self._shipId is None:
            return False, False
        burning = _as_bool(self._tryCall(battle.isVehicleBurning, self._shipId), False)
        flooding = _as_bool(self._tryCall(battle.isVehicleFlooding, self._shipId), False)
        return burning, flooding

    # ------------------------------------------------------------------
    # Damage events (dual-track, see SPEC §4.1)
    # ------------------------------------------------------------------

    def _selfShipIdFresh(self):
        """Self ship id straight from the game (no cache). None if unavailable."""
        try:
            ship = battle.getSelfPlayerShip()
            return getattr(ship, '_Ship__id', None) if ship is not None else None
        except Exception:
            return None

    def _matchSelf(self, otherId):
        """Is `otherId` our ship? Re-resolves the ship ONCE when the cache looks
        stale, instead of silently rejecting the event.

        Why this exists (2026-10-02): the ship/id pair used to be cached for the
        whole client session, so from the second battle on every damage callback
        compared against the previous battle's id and dropped our own ship's
        damage - no throws, no flinches, and `isVehicleBurning` was handed an id
        that no longer existed (fires/floods stuck at 0). The per-battle reset in
        `on_battle_shown` is the primary fix; this is the safety net (and it logs,
        so a stale cache can never hide again).
        """
        if otherId == self._shipId:
            return True
        fresh = self._selfShipIdFresh()
        if fresh is None or fresh != otherId:
            return False        # genuinely not us (other ships hit nearby)
        old = self._shipId
        self._ship = None
        self._shipId = None
        self._avatarId = None          # re-resolve: a new vehicle -> new avatar id
        self._ensureShip()
        if not self._shipIdRefreshed:
            self._shipIdRefreshed = True
            self._log('self ship id was stale ({} -> {}): cache refreshed on a '
                      'damage event'.format(old, self._shipId))
        return True

    def _onDamages(self, victimId, damages):
        # 'damages' aggregate track: every damage entry on our ship,
        # including fire/flood ticks and ramming. No type info available.
        if not self._inBattle:
            return
        try:
            if not self._matchSelf(victimId):
                return
            if not self._damagesDebugLogged:
                self._damagesDebugLogged = True
                self._log('damages debug: victimId={} shipId={} entries={}'.format(
                    victimId, self._shipId, len(damages) if damages else 0))
            for entry in damages or []:
                amount = self._num(self._safeField(entry, 'damage'))
                if amount <= 0:
                    continue
                self._writeMessage({
                    'type': 'damage_taken',
                    'source': 'damages',
                    'amount': amount,
                })
        except Exception as e:
            self._logError('onDamages failed: {}'.format(repr(e)))

    def _onShellInfo(self, *args, **kwargs):
        # Per-shell impact track (docs order): victimID, shooterID, ammoID,
        # matID, shootID, booleans(bitmask), damage, shotPosition, yaw, hlinfo.
        if not self._inBattle or not args:
            return
        try:
            victimId = args[0]
            if not self._matchSelf(victimId):
                return
            booleans = args[5] if len(args) > 5 else None
            damage = self._num(args[6]) if len(args) > 6 else 0
            hlinfo = args[9] if len(args) > 9 else None
            salvo = None
            if isinstance(hlinfo, (tuple, list)) and len(hlinfo) >= 2:
                salvo = hlinfo[-1]
                if salvo == -1:
                    salvo = None  # -1 is the engine's "no salvo" sentinel
            flags = None
            try:
                flags = int(booleans)
            except Exception:
                pass
            killed = False
            if flags is not None:
                # Bit order follows the events.md documentation; bit3 is the
                # "ship is destroyed" flag (consistent with the logged sample
                # where 32769 = bit0 'our ship was damaged' + unknown bit15).
                killed = bool(flags & (1 << 3))
            if not self._shellDebugLogged:
                # One-shot dump so the mask/ammo semantics can be pinned
                # against a real battle (M3 mapping milestone).
                self._shellDebugLogged = True
                ammoID = args[2] if len(args) > 2 else None
                matID = args[3] if len(args) > 3 else None
                self._log('shell debug: victim={} ammoID={} matID={} '
                          'booleans={!r} damage={} hlinfo={!r}'.format(
                              victimId, ammoID, matID, booleans, damage, hlinfo))
                ammoInfo = self._tryCall(battle.getAmmoParams, ammoID)
                if ammoInfo is not None:
                    try:
                        members = sorted(str(n) for n in dir(ammoInfo)
                                         if not str(n).startswith('__'))
                        self._log('ammo params members: {}'.format(','.join(members)[:500]))
                    except Exception:
                        pass
            if damage <= 0:
                return  # ricochet / no-penetration shells dealt no damage
            msg = {
                'type': 'damage_taken',
                'source': 'shell',
                'amount': damage,
                'salvo': salvo,
            }
            if flags is not None:
                msg['flags'] = flags
                msg['killed'] = killed
            self._writeMessage(msg)
        except Exception as e:
            self._logError('onShellInfo failed: {}'.format(repr(e)))

    # ------------------------------------------------------------------
    # Ship / meta resolution
    # ------------------------------------------------------------------

    def _ensureShip(self):
        if self._ship is not None:
            return
        try:
            ship = battle.getSelfPlayerShip()
            if ship is not None:
                self._ship = ship
                self._shipId = getattr(ship, '_Ship__id', None)
                self._log('Self ship resolved (id={})'.format(self._shipId))
        except Exception:
            pass  # silent: this runs every tick until the ship exists

    def _collectBattleStart(self):
        msg = {'type': 'battle_start'}
        self._ensureShip()
        if self._ship is not None:
            msg['ship_name'] = self._safeField(self._ship, 'name')
            msg['ship_type'] = self._safeField(self._ship, 'subtype')
        playerInfo = self._tryCall(battle.getSelfPlayerInfo)
        if playerInfo is not None:
            msg['player_name'] = self._safeField(playerInfo, 'name')
        return msg

    # ------------------------------------------------------------------
    # File bridge
    # ------------------------------------------------------------------

    def _openFile(self, fresh):
        # File lifecycle (same convention as the dglab reference mod): the
        # file only ever holds the current battle's data. `fresh` truncates
        # it at battle start; on battle quit _clearOutput empties it again.
        self._closeFile()
        for path in self._pathCandidates():
            try:
                exists = self._tryCall(utils.isPathExists, path)
                if fresh or not exists:
                    # Engine `open` does not silently create missing files —
                    # it logs "Path ... does not exists" and returns None, so
                    # create/truncate with 'wb' semantics first (proven by
                    # Aslain's cfg writes).
                    f = open(path, 'wb')
                    if f is None:
                        self._logError('engine open(wb) returned None for {}'.format(path))
                        continue
                    f.close()
                    if fresh:
                        self._log('Output cleared for new battle: {}'.format(path))
                f = open(path, 'ab')
                if f is None:
                    self._logError('engine open(ab) returned None for {}'.format(path))
                    continue
                self._file = f
                self._path = path
                self._log('Output: {}'.format(path))
                return True
            except Exception as e:
                self._logError('cannot open {}: {}'.format(path, e))
        return False

    def _clearOutput(self):
        # Empty the file when leaving a battle, mirroring the reference mod.
        try:
            path = self._path
            if path is None:
                return
            f = open(path, 'wb')
            if f is None:
                return
            f.close()
            self._log('Output cleared (battle quit): {}'.format(path))
        except Exception as e:
            self._logError('clear output failed: {}'.format(e))

    def _closeFile(self):
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def _pathCandidates(self):
        candidates = []
        # Sandbox CWD is the mod folder, so relative paths do not reach the
        # game root. Absolute path via getModDir() + 5 levels up lands on the
        # game root (same recipe as Aslain's CONFIG_PATH='../../../../../profile').
        modDir = self._tryCall(utils.getModDir)
        if modDir:
            candidates.append(modDir + '/../../../../../profile/' + OUTPUT_NAME)
        # Last-resort fallbacks (engine may or may not allow writes here).
        candidates.append(OUTPUT_NAME)
        candidates.append('profile/' + OUTPUT_NAME)
        return candidates

    def _writeMessage(self, msg):
        if not self._inBattle:
            return
        try:
            if self._file is None:
                if not self._openFile(fresh=False):
                    self._rateLimitedLog('no output file; message dropped')
                    return
            self._seq += 1
            msg['ts'] = int(time.time() * 1000)
            msg['bt'] = self._battleTime()
            msg['seq'] = self._seq
            self._file.write(self._encodeLine(msg))
            self._file.flush()
        except Exception as e:
            self._logError('write failed: {}'.format(e))

    def _battleTime(self):
        try:
            return round(float(utils.getTimeFromGameStart()), 3)
        except Exception:
            return 0.0

    def _encodeLine(self, msg):
        try:
            return utils.jsonEncode(msg) + '\n'
        except Exception as e:
            self._logError('jsonEncode failed ({}); using manual encoder'.format(e))
            return self._manualJson(msg) + '\n'

    def _manualJson(self, msg):
        # Fallback only. Message fields are flat and simple.
        parts = []
        for key in sorted(msg.keys()):
            parts.append('"{}":{}'.format(self._quote(key), self._manualValue(msg[key])))
        return '{' + ','.join(parts) + '}'

    def _manualValue(self, value):
        if value is None:
            return 'null'
        if value is True:
            return 'true'
        if value is False:
            return 'false'
        if isinstance(value, _INT_TYPES):
            return repr(value)
        return '"{}"'.format(self._quote(value))

    def _quote(self, text):
        out = str(text)
        out = out.replace('\\', '\\\\').replace('"', '\\"')
        out = out.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _tryCall(self, func, *args):
        try:
            return func(*args)
        except Exception:
            return None

    def _safeField(self, obj, name):
        try:
            value = getattr(obj, name, None)
            if value is None and isinstance(obj, dict):
                value = obj.get(name)
            return value
        except Exception:
            return None

    def _num(self, value):
        try:
            if value is None:
                return 0
            return int(round(float(value)))
        except Exception:
            return 0

    def _hpPct(self, health, maxHealth):
        try:
            if not maxHealth:
                return 0
            return round(100.0 * health / maxHealth, 1)
        except Exception:
            return 0

    def _rateLimitedLog(self, message):
        now = time.time()
        if now >= self._nextLogTime:
            self._nextLogTime = now + LOG_INTERVAL_SEC
            self._logError(message)


def _as_bool(value, default):
    if value is None:
        return default
    return bool(value)
