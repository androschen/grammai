"""Conservative duplicate-prefix trimming, enabled only for actual audio overlap."""
import re

_UNITS=re.compile(r'[\u3400-\u9fff]|[^\W_]+',re.UNICODE)


def trim_overlap(previous,current,seconds):
    if seconds<=0 or not previous or not current:
        return current
    before=list(_UNITS.finditer(previous))
    after=list(_UNITS.finditer(current))
    # Restrict matching to a plausible amount of speech within the shared audio.
    maximum=min(len(before),len(after),max(2,min(8,round(seconds*10))))
    for count in range(maximum,1,-1):
        left=[item.group().casefold() for item in before[-count:]]
        right=[item.group().casefold() for item in after[:count]]
        if left==right:
            # Keep very short whole-utterance repetitions; never erase a reply like "对对".
            if count==len(after):
                return current
            return current[after[count].start():].lstrip()
    return current
