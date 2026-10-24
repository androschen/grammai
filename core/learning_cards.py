"""Pure text presentation for learning cards; never loads a model."""
import re


def vocabulary_card(item):
    return item.get('card_type')=='vocabulary'


def practice_prompt(item,mode='understand'):
    expression=item.get('native_text','')
    if mode=='recall' and vocabulary_card(item):
        sentence=item.get('example_sentence','')
        if expression and expression in sentence:
            # Latin words should not blank matching letters inside other words.
            pattern=re.escape(expression)
            if expression[0].isascii() and expression[0].isalnum():pattern=r'(?<!\w)'+pattern
            if expression[-1].isascii() and expression[-1].isalnum():pattern+=r'(?!\w)'
            blanked,count=re.subn(pattern,'____',sentence)
            if not count:blanked=sentence.replace(expression,'____',1)
            return blanked,item.get('target_text','')
    if mode=='recall':
        return item.get('target_text',''),''
    return item.get('example_sentence','') if vocabulary_card(item) else expression,''


def answer_text(item,mode='understand'):
    expression=item.get('native_text','');meaning=item.get('target_text','')
    return expression+'\n'+meaning if vocabulary_card(item) or mode=='recall' else meaning


def card_search_text(item):
    return ' '.join(str(item.get(k,'')) for k in ('native_text','target_text','native_phonetics','notes','usage_note','example_sentence'))
