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
LUCK_STROKES = [1, 3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18, 21, 23, 24, 25, 26, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41,42,43,44,45,47,48,49,51,52,53,57,58]
MAX_STROKES  = 16
MAX_LETTERS  = 2

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
    lucks = [
        sum(family_strokes),
        family_strokes[1] + first_strokes[0],
        sum(first_strokes),
        sum(family_strokes[:-1]) + sum(first_strokes[1:]),
        sum(family_strokes) + sum(first_strokes),
    ]
    is_valids = map(lambda a: a in LUCK_STROKES, lucks)
    return reduce(lambda a,b: a and b, is_valids)

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
def get_c(code, all_codes):
    news = ','.join(map(lambda a: str(a), all_codes['new'][code]))
    olds = ','.join(map(lambda a: str(a), all_codes['old'][code]))
    return u'%s(%s/%s)' % (unichr(code), news, olds)

#---------------------------------------
def check(args):

    all_codes, valid_code, target_strokes = (args)
    print 'checking "%X"...' % valid_code

    intersection = lambda a,b: len(set(a) & set(b)) > 0

    result = []
    for check_code in all_codes['new'].keys():

        if not intersection(all_codes['new'][check_code], target_strokes): continue
        if not intersection(all_codes['old'][check_code], target_strokes): continue

        result.append(check_code)

    return (valid_code, result)

#---------------------------------------
def detect_func(args):

    master_code, all_codes, new_valids, old_valids = (args)
    print 'checking "%X"...' % master_code

    new_stroke  = all_codes['new'][master_code][0] # 新字体は１文字である事を保証して、プログラムをシンプルにする
    old_strokes = all_codes['old'][master_code]

    intersection = lambda a,b: len(set(a) & set(b)) > 0

    if not new_valids.has_key(new_stroke): return
    if len(old_strokes) > 0 and not intersection(old_strokes, old_valids.keys()): return

    # 1文字目確定
    result = []

    # 2文字目が不要なパターンを評価
    if 0 in new_valids[new_stroke]:
        result.append('')  # 2文字目不要を明示

    # 2文字目
    for master_code2 in sorted(all_codes['new'].keys()):
                    
        new_stroke2  = all_codes['new'][master_code2][0] # 新字体は１文字である事を保証して、プログラムをシンプルにする
        old_strokes2 = all_codes['old'][master_code2]

        if not new_stroke2 in new_valids[new_stroke]: continue
        if len(old_strokes2) > 0 and not intersection(old_strokes2, old_valids.keys()): continue

        result.append(master_code2)

    return (master_code, result)

#---------------------------------------
def get_relative(all_codes, new_valids, old_valids):

    args = [(c, all_codes, new_valids, old_valids) for c in sorted(all_codes['new'].keys())]
    result = Pool().map(detect_func, args)
    result = filter(lambda a: a != None, result)
    result = dict(result)

    """
    intersection = lambda a,b: len(set(a) & set(b)) > 0
    result = {}
    for master_code in sorted(all_codes['new'].keys()):

        print 'checking "%X"...' % master_code

        new_stroke  = all_codes['new'][master_code][0] # 新字体は１文字である事を保証して、プログラムをシンプルにする
        old_strokes = all_codes['old'][master_code]

        if not new_valids.has_key(new_stroke): continue
        if len(old_strokes) > 0 and not intersection(old_strokes, old_valids.keys()): continue

        # 1文字目確定
        result[master_code] = []

        # 2文字目が不要なパターンを評価
        if 0 in new_valids[new_stroke]:
            result[master_code].append('')  # 2文字目不要を明示

        # 2文字目
        for master_code2 in sorted(all_codes['new'].keys()):
                        
            new_stroke2  = all_codes['new'][master_code2][0] # 新字体は１文字である事を保証して、プログラムをシンプルにする
            old_strokes2 = all_codes['old'][master_code2]

            if not new_stroke2 in new_valids[new_stroke]: continue
            if len(old_strokes2) > 0 and not intersection(old_strokes2, old_valids.keys()): continue

            result[master_code].append(master_code2)
    """
    return result

#---------------------------------------
if __name__ == '__main__':

    start_time = time.time()

    new_valids  = get_valid_strokes([12,5])
    old_valids  = get_valid_strokes([13,5])
    jis0208     = load_jis0208()
    all_codes   = load_strokes(jis0208)
    all_codes   = split_new_old(all_codes)

    """
    print '---- new_valids ----'
    for k,v in new_valids.items(): print '%d : %s' % (k, str(v))
    print '---- old valids ----'
    for k,v in old_valids.items(): print '%d : %s' % (k, str(v))
    print '---- new codes ----'
    for k,v in sorted(all_codes['new'].items(), key = lambda a: a[0]): print '%X : %s' % (k, str(v))

    """
    result = get_relative(all_codes, new_valids, old_valids)

    """
    result_new  = get_strokes(all_codes['new'], new_valids)
    result_old  = get_strokes(all_codes['old'], old_valids)

    args = [(all_codes, k, v) for k, v in result_new.items()]
    result = Pool().map(check, args)
    result = dict(result)

    result = {}
    intersection = lambda a,b: len(set(a) & set(b)) > 0
    for valid_code, target_strokes in :

        print 'checking "%X"...' % valid_code
        result[valid_code] = []
        for check_code in all_codes['new'].keys():

            if not intersection(all_codes['new'][check_code], target_strokes): continue
            if not intersection(all_codes['old'][check_code], target_strokes): continue

            result[valid_code].append(check_code)
    """

    print 'writing result file...'
    with codecs.open('./out.csv', 'w','utf-8-sig') as f:
        for k,v in sorted(result.items(), key = lambda a: a[0]):
            f.write(get_c(k, all_codes))
            f.write(',')
            for chr in map(lambda a: get_c(a, all_codes), v):
                f.write(chr)
                f.write(',')
            f.write('\r\n')

    print 'total time = %f' % (time.time() - start_time)
