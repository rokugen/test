# -*- coding: utf-8 -*-
import os
import re
import mmap
import struct
import csv
import traceback
import json
import codecs
import time

from multiprocessing import Pool

STROKES_FILE = u'./ucs-strokes.txt'

# http://akachan-meimei.com/
#LUCK_STROKES 　= [1, 3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18, 21, 23, 24, 25,     27,         31, 32, 33,     35, 36, 37, 38, 39,     41, 42,         45, 47, 48,     51, 52, 53, 57, 58, 61, 63, 65, 67, 68]  # 69以上は調べていない。
# http://www.koufuku.ne.jp/happyseimei/
#LUCK_STROKES = [   3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18, 21, 23, 24, 25,     27, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 47, 48, 49, 51, 52, 53] # 54以上は全て凶になる。また、名前が1文字の場合の地格の数え方が特殊(+1したいらしい)
# 本1
#LUCK_STROKES = [1, 3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18, 21, 23, 24, 25, 26, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 47, 48, 49, 51, 52, 53, 57, 58]
# http://www.s-kougen.com/kakusu/index.htm
#LUCK_STROKES = [1, 3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18, 21, 23, 24, 25,         29,     31, 32, 33,             37, 39,         41,         45,     47, 48,         52,     57, 58, 61, 63, 65, 67, 68, 71, 73, 75, 77, 78, 81]
# 本「たまひよ　赤ちゃんのしあわせ名前事典2014～2015版」
LUCK_STROKES  = [1,3,5,6,7,8,11,13,15,16,17,18,21,23,24,25,27,29,31,32,33,35,36,37,38,39,41,42,45,47,48,50,51,52,53,57,58,63,65,67,68,71,72,73,77,78,81]

MAX_STROKES  = 100
MAX_LETTERS  = 2
OLD_STROKE_ENABLE = False

#---------------------------------------
def get_valid_strokes(family_strokes):

    valids = {}
    for i in range(1, MAX_STROKES + 1):     # 1文字目
        for j in range(0, MAX_STROKES + 1): # 2文字目
            if not is_valid(family_strokes, [i,j]): continue
            if not valids.has_key(i): valids[i] = []
            valids[i].append(j)

    return valids

#---------------------------------------
def is_valid(family_strokes, first_strokes):

    # 名前の2文字目が0画の時は地格と外画に霊数を与える
    if first_strokes[1] == 0:
        stroke_2 = sum(first_strokes) + 1
        stroke_3 = sum(family_strokes[:-1]) + 1                         # 注意：流派によって違う
    else:
        stroke_2 = sum(first_strokes) + 0
        stroke_3 = sum(family_strokes[:-1]) + sum(first_strokes[1:])    # 注意：流派によって違う
    
    lucks = [
        sum(family_strokes),
        family_strokes[1] + first_strokes[0],
        stroke_2,
        stroke_3,
        sum(family_strokes) + sum(first_strokes),
    ]
    is_valids = map(lambda a: a in LUCK_STROKES, lucks)
    return reduce(lambda a,b: a and b, is_valids)

#---------------------------------------
def load_sound():
    sounds = {}
    with codecs.open('./Unihan-kJapaneseOnKun.txt', 'r','utf-8-sig') as f:
        for line in f.readlines():
            words = line.strip().split('\t')
            try:
                code  = ord(words[0])
            except TypeError:
                continue
            kun   = words[1].split(' ')
            on    = words[2].split(' ') if len(words) >= 3 else []
            sounds[code] = { 'kun' : kun, 'on' : on }
    return sounds

#---------------------------------------
def load_jis0208():
    lines = file('./JIS0208.TXT', 'r').readlines()
    lines = filter(lambda a: a[0] != '#', lines)
    lines = map(lambda a: a.split('\t')[2], lines)
    lines = map(lambda a: int(a, 16), lines)
    return lines
    
#---------------------------------------
def load_strokes(jis0208):

    codes = {}
    lines = file(STROKES_FILE, 'r').readlines()

#    in_range = lambda a: (a >= 0x3400 and a <= 0x9FFF) or (a >= 0xF900 and a <= 0xFAFF) or (a >= 0x20000 and a <= 0x2FFFF)
    in_range = lambda a: (a >= 0x4E00 and a <= 0x9FFF)

    for line in lines:
        if not re.match('U\+(\S+)\t.+', line): continue
        line = line.strip()
        code = re.sub('U\+(\S+)\t.+', r'\1', line)
        code = int(code, 16)
        strokes = re.sub('U\+\S+\t(\S+)', r'\1', line)
        strokes = strokes.split(',')

        if not in_range(code): continue # 参考：http://tama-san.com/?p=196
#        if not valid_c(code):  continue # UCS2範囲外な文字を除外
        if not code in jis0208: continue # 第１水準・第２水準以外を除外
        codes[code] = map(lambda a: int(a), strokes)

    return codes

#---------------------------------------
def split_new_old(all):
    temp = {'new' : {}, 'old' : {}}
    for code, strokes in all.items():
        temp['new'][code] = strokes[:1]
        temp['old'][code] = strokes[1:] if len(strokes) >= 2 else []
    return temp

#---------------------------------------
def get_strokes(codes, valids):
    results = {}
    for code, strokes in codes.items():
        valid_strokes = []
        for stroke in strokes:
            if valids.has_key(stroke):
                valid_strokes.extend(valids[stroke])
        results[code] = sorted(list(set(valid_strokes)))
    return results

#---------------------------------------
def valid_c(code):
    try:
        unichr(code)
    except ValueError:
        return False
    return True

#---------------------------------------
def get_c(code):
    return u'%s' % (unichr(code))

#---------------------------------------
def detect_func(args):

    master_code, all_codes, new_valids, old_valids = (args)

    print 'checking "%X"...' % master_code

    new_stroke = all_codes['new'][master_code][0]     # 新字体の画数が1通りである事を保証して、プログラムをシンプルにする
    if len(all_codes['old'][master_code]) > 0:
        old_stroke = all_codes['old'][master_code][0] # 旧字体も同様に処理
    else:
        old_stroke = new_stroke                       # 旧字体が存在しない場合は新字体を参照する

    if not new_valids.has_key(new_stroke): return
    if not old_valids.has_key(old_stroke): return

    # 1文字目確定
    result = []

    # 2文字目が不要なパターンを評価
    if 0 in new_valids[new_stroke]:
        result.append('')  # 2文字目不要を明示

    # 2文字目
    for master_code2 in sorted(all_codes['new'].keys()):

        new_stroke2  = all_codes['new'][master_code2][0]     # 新字体の画数が1通りである事を保証して、プログラムをシンプルにする
        if len(all_codes['old'][master_code2]) > 0:
            old_stroke2 = all_codes['old'][master_code2][0] # 旧字体も同様に処理
        else:
            old_stroke2 = new_stroke2                       # 旧字体が存在しない場合は新字体を参照する

        if not new_stroke2 in new_valids[new_stroke]: continue
        if not old_stroke2 in old_valids[old_stroke]: continue

        result.append(master_code2)

    # 候補が0件だった場合は選考落ち
    if len(result) == 0: return

    return (master_code, result)

#---------------------------------------
def get_relative(all_codes, new_valids, old_valids):

    args = [(c, all_codes, new_valids, old_valids) for c in sorted(all_codes['new'].keys())]
    result = Pool().map(detect_func, args)
    result = filter(lambda a: a != None, result)
    result = dict(result)

    return result

#---------------------------------------
def write_result(result, all_codes, sounds):

    print 'writing result file...'
    with codecs.open('./out.csv', 'w','utf-8-sig') as f:
        sort_func = lambda a: (all_codes['new'][a[0]][0], a[0]) # key0:画数, key1:文字コード
        for k,v in sorted(result.items(), key = sort_func):
            f.write(get_c(k))
            f.write(',')
            f.write('%d' % all_codes['new'][k][0])
            f.write(',')

            if sounds.has_key(k):
                on_values  = [sound for sound in sounds[k]['on']]
                kun_values = [sound for sound in sounds[k]['kun']]
                f.write('"%s"' % u', '.join(on_values))
                f.write(',')
                f.write('"%s"' % u', '.join(kun_values))
            else:
                f.write(',')

            f.write(',')

            # 1字名が認められていた場合
            single_is_valid = '' in v

            if single_is_valid: v = filter(lambda a: a != '', v)    # いったんソートから除外
            tmp = sorted(v, key = lambda a: (all_codes['new'][a], a))
            if single_is_valid: f.write(',')                        # 空白セルを書き込む

            for chr in map(lambda a: get_c(a), tmp):
                f.write(chr)
                f.write(',')
            f.write('\r\n')

#---------------------------------------
if __name__ == '__main__':

    start_time = time.time()

    new_valids  = get_valid_strokes([12,5])

    # 旧字体が有効なら新字体同様に画数を検出
    if OLD_STROKE_ENABLE:
        old_valids  = get_valid_strokes([13,5])
    # 旧字体が無効なら全ての組み合わせを「有効な画数」として与える
    else:
        old_valids = {}
        for i in range(MAX_STROKES):
            old_valids[i] = range(MAX_STROKES)

    for k,v in new_valids.items(): print k,v
    if OLD_STROKE_ENABLE:
        for k,v in old_valids.items(): print k,v

    sounds      = load_sound()

    jis0208     = load_jis0208()
    all_codes   = load_strokes(jis0208)
    all_codes   = split_new_old(all_codes)

    result = get_relative(all_codes, new_valids, old_valids)
    write_result(result, all_codes, sounds)

    print 'total time = %f' % (time.time() - start_time)

