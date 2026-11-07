# -*- coding: utf-8 -*-
# ExportShipStatus — WOWS own-ship telemetry exporter (official PnFMods Mods API).
# Entry point. Mirrors the load contract proven by installed Aslain mods
# (DamageMonitor / HidingTimer): engine scans res_mods/PnFMods/<Mod>/Main.py
# and executes it at client start; module-level instance subscribes events.

API_VERSION = 'API_v1.0'
MOD_NAME = 'ExportShipStatus'

try:
    import battle, events, dataHub, ui, constants, utils, callbacks
except Exception:
    pass

from core import TelemetryCore


def logInfo(*args):
    data = [str(i) for i in args]
    utils.logInfo('[{}] {}'.format(MOD_NAME, ', '.join(data)))


def logError(*args):
    data = [str(i) for i in args]
    utils.logError('[{}] {}'.format(MOD_NAME, ', '.join(data)))


gCore = None
try:
    gCore = TelemetryCore(logInfo, logError)
    events.onBattleShown(gCore.on_battle_shown)
    events.onBattleEnd(gCore.on_battle_end)
    events.onBattleQuit(gCore.on_battle_quit)
    logInfo('Created instance, waiting for battle')
except Exception as e:
    logError('Init failed: {}'.format(e))
