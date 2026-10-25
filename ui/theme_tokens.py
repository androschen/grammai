"""Shared colors for every GrammAI workspace and reading component."""
PALETTES={
 'dark':dict(bg='#151a18',surface='#1c2320',soft='#262e29',ink='#ebf2ed',muted='#a0b1a6',line='#303c34',accent='#a5dfbd',wash='#2a4032',green='#a5dfbd',alert='#eab09a',zh='#deb77e',th='#97c9bc',en='#adc0e7',id='#d5a6bc'),
 'light':dict(bg='#f5f7f6',surface='#ffffff',soft='#edf1ef',ink='#26362e',muted='#64756b',line='#dfe7e2',accent='#286f50',wash='#e4f1e9',green='#286f50',alert='#9b4f35',zh='#875d25',th='#407268',en='#526ca0',id='#94526d'),
}


def palette_for(theme='dark'):
 return PALETTES.get(theme,PALETTES['dark'])
