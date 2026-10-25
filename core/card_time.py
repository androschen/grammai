"""Present immutable UTC card timestamps in local time without migrating user data."""
from datetime import datetime,timedelta


def saved_time(value,now=None):
    """Return compact label and full tooltip. Missing dates are never invented."""
    try:
        if not isinstance(value,str):raise ValueError('Missing timestamp')
        stamp=datetime.fromisoformat(value)
        if stamp.tzinfo is None or stamp.utcoffset() is None:raise ValueError('Missing time zone')
        local=stamp.astimezone() if now is None else stamp.astimezone(now.tzinfo)
        current=datetime.now().astimezone() if now is None else now
    except (ValueError,TypeError,OverflowError,OSError):
        return 'Date unavailable','The original save time was not recorded or is invalid.'
    day=local.date()
    prefix='Today' if day==current.date() else ('Yesterday' if day==current.date()-timedelta(days=1) else local.strftime('%d %b %Y'))
    short=prefix+', '+local.strftime('%H:%M')
    offset=local.strftime('%z');offset=offset[:3]+':'+offset[3:]
    full=local.strftime('%d %B %Y, %H:%M:%S')+' (UTC'+offset+')'
    return short,full


def saved_caption(value):
    short,full=saved_time(value)
    if short=='Date unavailable':return 'Saved time unavailable',full
    return ('Saved '+short[:1].lower()+short[1:] if short.startswith(('Today','Yesterday')) else 'Saved '+short),full
