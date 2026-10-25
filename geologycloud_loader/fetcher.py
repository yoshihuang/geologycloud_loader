# -*- coding: utf-8 -*-
"""Asynchronous downloads from the Geology Cloud API.

* Uses QgsNetworkAccessManager, so the QGIS proxy / SSL settings apply.
* Only the newest request per dataset counts: a new map extent aborts the
  previous download, and late answers are discarded by a generation number.
* At most ``MAX_ACTIVE`` downloads run at once; large answers are parsed in a
  background QgsTask so the map stays responsive.
"""

import time
from functools import partial

from qgis.PyQt.QtCore import QObject, QTimer, QUrl, QUrlQuery, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsApplication, QgsNetworkAccessManager, QgsTask

from .geojson_parser import ServiceError, parse_feature_collection

USER_AGENT = b"QGIS-GeologyCloudLoader/1.0"
MAX_ACTIVE = 3
TIMEOUT_MS = 90000
BACKGROUND_PARSE_BYTES = 1500000


def build_url(dataset, bbox):
    """Request URL.  ``bbox`` is validated here: the service silently returns
    the WHOLE island when the bbox is malformed, which must never happen."""
    xmin, ymin, xmax, ymax = (float(v) for v in bbox)
    if not (xmin < xmax and ymin < ymax):
        raise ValueError("invalid bbox %r" % (bbox,))
    if not (-180 <= xmin <= 180 and -180 <= xmax <= 180 and -90 <= ymin <= 90 and -90 <= ymax <= 90):
        raise ValueError("bbox outside lon/lat range %r" % (bbox,))
    url = QUrl(dataset.url)
    query = QUrlQuery()
    query.addQueryItem("all", "true")
    query.addQueryItem("bbox", "%.6f,%.6f,%.6f,%.6f" % (xmin, ymin, xmax, ymax))
    url.setQuery(query)
    return url


def _parse_in_task(task, payload, geometry):
    return parse_feature_collection(payload, geometry)


class Fetcher(QObject):
    started = pyqtSignal(str)
    finished = pyqtSignal(str, object, int, float)   # key, rows, skipped, seconds
    failed = pyqtSignal(str, str)                     # key, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation = {}
        self._queue = []          # [(dataset, bbox, generation)]
        self._replies = {}        # key -> (reply, timer)
        self._tasks = {}          # key -> QgsTask
        self._alive = set()       # keep Python wrappers alive until finished
        self._started_at = {}

    # -- public -----------------------------------------------------------
    def fetch(self, dataset, bbox):
        key = dataset.key
        self.cancel(key)
        generation = self._generation.get(key, 0) + 1
        self._generation[key] = generation
        self._queue.append((dataset, tuple(bbox), generation))
        self.started.emit(key)
        self._pump()

    def cancel(self, key):
        self._generation[key] = self._generation.get(key, 0) + 1
        self._queue = [item for item in self._queue if item[0].key != key]
        entry = self._replies.pop(key, None)
        if entry is not None:
            reply, timer = entry
            timer.stop()
            reply.abort()
            reply.deleteLater()
        task = self._tasks.pop(key, None)
        if task is not None:
            task.cancel()
        self._pump()

    def cancel_all(self):
        for key in list(self._generation):
            self.cancel(key)

    def is_busy(self, key):
        return key in self._replies or key in self._tasks or any(i[0].key == key for i in self._queue)

    # -- internals ---------------------------------------------------------
    def _pump(self):
        while self._queue and len(self._replies) < MAX_ACTIVE:
            dataset, bbox, generation = self._queue.pop(0)
            self._start(dataset, bbox, generation)

    def _start(self, dataset, bbox, generation):
        key = dataset.key
        try:
            url = build_url(dataset, bbox)
        except ValueError as exc:
            self.failed.emit(key, str(exc))
            return
        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", USER_AGENT)
        request.setRawHeader(b"Accept", b"application/json")
        reply = QgsNetworkAccessManager.instance().get(request)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(partial(self._timeout, key, generation))
        timer.start(TIMEOUT_MS)
        self._replies[key] = (reply, timer)
        self._started_at[key] = time.monotonic()
        reply.finished.connect(partial(self._reply_finished, dataset, generation, reply))

    def _timeout(self, key, generation):
        if self._generation.get(key) != generation:
            return
        entry = self._replies.pop(key, None)
        if entry is not None:
            entry[0].abort()
            entry[0].deleteLater()
        self.failed.emit(key, "連線逾時（%d 秒），請縮小地圖範圍後再試" % (TIMEOUT_MS // 1000))
        self._pump()

    def _reply_finished(self, dataset, generation, reply):
        key = dataset.key
        current = self._replies.get(key)
        if self._generation.get(key) != generation or current is None or current[0] is not reply:
            reply.deleteLater()
            return
        self._replies.pop(key)[1].stop()
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.failed.emit(key, "下載失敗：%s" % reply.errorString())
                return
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if status is not None and int(status) >= 400:
                self.failed.emit(key, "服務回應 HTTP %s" % status)
                return
            payload = bytes(reply.readAll())
        finally:
            reply.deleteLater()
            self._pump()

        if len(payload) < BACKGROUND_PARSE_BYTES:
            try:
                rows, skipped = parse_feature_collection(payload, dataset.geometry)
            except ServiceError as exc:
                self.failed.emit(key, str(exc))
                return
            self._emit_finished(key, rows, skipped)
            return

        holder = {}
        task = QgsTask.fromFunction(
            "地質雲：解析 %s" % dataset.title, _parse_in_task, payload, dataset.geometry,
            on_finished=partial(self._task_finished, key, generation, holder),
            flags=QgsTask.Flag.CanCancel | QgsTask.Flag.Silent)
        holder["task"] = task
        self._alive.add(task)
        self._tasks[key] = task
        QgsApplication.taskManager().addTask(task)

    def _task_finished(self, key, generation, holder, exception, result=None):
        self._alive.discard(holder.get("task"))
        if self._generation.get(key) != generation:
            return
        self._tasks.pop(key, None)
        if exception is not None or result is None:
            message = str(exception) if exception is not None else "解析已取消"
            self.failed.emit(key, message)
            return
        rows, skipped = result
        self._emit_finished(key, rows, skipped)

    def _emit_finished(self, key, rows, skipped):
        seconds = time.monotonic() - self._started_at.pop(key, time.monotonic())
        self.finished.emit(key, rows, skipped, seconds)
