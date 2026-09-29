
from datetime import datetime

import pytz

EPOCH = datetime(1970, 1, 1)


def datetime_to_epoch(dttm):
    if dttm.tzinfo:
        dttm = dttm.replace(tzinfo=pytz.utc)
        epoch_with_tz = pytz.utc.localize(EPOCH)
        return (dttm - epoch_with_tz).total_seconds() * 1000
    return (dttm - EPOCH).total_seconds() * 1000


def now_as_float():
    # py3.12: datetime.utcnow 弃用; replace(tzinfo=None) 保持原 naive-UTC 语义
    return datetime_to_epoch(datetime.now(pytz.utc).replace(tzinfo=None))
