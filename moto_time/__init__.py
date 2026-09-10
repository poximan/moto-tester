"""Proveedor temporal comun de Moto Tester."""
from datetime import datetime, timedelta, timezone
import logging
import time

class TimeProvider:
    def epoch_seconds(self):
        return time.time()

    def monotonic_seconds(self):
        return time.monotonic()

    def sleep(self, seconds):
        time.sleep(seconds)

    def log_timestamp(self, epoch):
        return datetime.fromtimestamp(epoch, timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")

clock = TimeProvider()

class PresentationFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return clock.log_timestamp(record.created)
