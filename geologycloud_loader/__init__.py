# -*- coding: utf-8 -*-
"""GeologyCloud Loader - load Taiwan Geology Cloud open data into QGIS.

Copyright (C) 2026 GeologyCloud Loader contributors

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 2 of the License, or (at your option) any later
version.
"""


def classFactory(iface):  # noqa: N802 (QGIS API name)
    from .plugin import GeologyCloudLoader
    return GeologyCloudLoader(iface)
