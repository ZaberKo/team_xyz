import os
import pickle
from collections import defaultdict
from itertools import count, zip_longest

import numpy as np

from config import *

abs_path = os.path.dirname(os.path.abspath(__file__))
data_path=os.path.join(abs_path,'data')
glove_file = os.path.join(data_path,data_config['glove_file'])
vocab_map_file = os.path.join(data_path,data_config['pickle_file'])

word_size = data_config['word_size']
emb_dim = data_config['emb_dim']
word_count_threshold = data_config['word_count_threshold']
char_count_threshold = data_config['char_count_threshold']

sanitize = str.maketrans({"|": None, "\n": None})
tsvs = 'train','dev', 'test'

bos = '<BOS>'
eos = '<EOS>'
unk = '<UNK>'
pad = ''
EMPTY_TOKEN = '<NULL>'
# pad (or trim) to word_size characters
pad_spec = '{0:<%d.%d}' % (word_size, word_size)


def populate_dicts(files):
    vocab = defaultdict(count().__next__)
    chars = defaultdict(count().__next__)
    wdcnt = defaultdict(int)
    chcnt = defaultdict(int)
    test_wdcnt = defaultdict(int)
    # all glove words in test/dev should be added to known, but non-glove words in test/dev should be kept unknown

    # count the words and characters to find the ones with cardinality above the thresholds
    for f in files:
        f = os.path.join('./data', f)
        with open('%s.tsv' % f, 'r', encoding='utf-8') as input_file:
            for line in input_file:
                if 'test' in f:
                    uid, title, context, query = line.split('\t')
                else:
                    uid, title, context, query, answer, raw_context, begin_answer, end_answer, raw_answer = line.split(
                        '\t')
                tokens = context.split(' ') + query.split(' ') + answer.split(' ')
                if 'train' in f:
                    for t in tokens:
                        wdcnt[t.lower()] += 1
                        for c in t: chcnt[c] += 1
                else:
                    for t in tokens:
                        test_wdcnt[t.lower()] += 1

    # add all words that are both in glove and the vocabulary first
    with open(glove_file, encoding='utf-8') as f:
        for line in f:
            word = line.split()[0].lower()
            if wdcnt[word] >= 1 or test_wdcnt[
                word] >= 1:  # polymath adds word to dict regardless of word_count_threshold when it's in GloVe
                _ = vocab[word]
    known = len(vocab)

    # add the special markers
    _ = vocab[bos]
    _ = vocab[eos]
    _ = vocab[pad]
    _ = vocab[unk]
    _ = chars[pad]
    _ = chars[unk]

    # finally add all words that are not in yet
    _ = [vocab[word] for word in wdcnt if word not in vocab and wdcnt[word] > word_count_threshold]
    _ = [chars[c] for c in chcnt if c not in chars and chcnt[c] > char_count_threshold]

    # return as defaultdict(int) so that new keys will return 0 which is the value for <unknown>
    return known, defaultdict(int, vocab), defaultdict(int, chars)


def tsv_iter(line, vocab, chars, is_test=False, misc={}):
    unk_w = vocab[unk]
    unk_c = chars[unk]

    if is_test:
        uid, title, context, query = line.split('\t')
        answer = ''
        begin_answer, end_answer = '0', '1'
    else:
        uid, title, context, query, answer, raw_context, begin_answer, end_answer, raw_answer = line.split('\t')
        # uid, title, context, query, begin_answer, end_answer, answer = line.split('\t')

    ctokens = context.split(' ')
    qtokens = query.split(' ')
    atokens = answer.split(' ')
    mtokens = []
    ba, ea = int(begin_answer), int(end_answer) - 1  # the end from tsv is exclusive

    if ba > ea:
        raise ValueError('answer problem with input line:\n%s' % line)

    if not is_test:
        mtokens = ctokens[ba:ea + 1]

    # replace EMPTY_TOKEN with ''
    ctokens = [t if t != EMPTY_TOKEN else '' for t in ctokens]
    qtokens = [t if t != EMPTY_TOKEN else '' for t in qtokens]
    atokens = [t if t != EMPTY_TOKEN else '' for t in atokens] + [eos]
    mtokens = [t if t != EMPTY_TOKEN else '' for t in mtokens]

    cwids = [vocab.get(t.lower(), unk_w) for t in ctokens]
    qwids = [vocab.get(t.lower(), unk_w) for t in qtokens]
    awids = [vocab.get(t.lower(), unk_w) for t in atokens]
    mwids = [vocab.get(t.lower(), unk_w) for t in mtokens]
    ccids = [[chars.get(c, unk_c) for c in t][:word_size] for t in ctokens]  # clamp at word_size
    qcids = [[chars.get(c, unk_c) for c in t][:word_size] for t in qtokens]
    acids = [[chars.get(c, unk_c) for c in t][:word_size] for t in atokens]
    mcids = [[chars.get(c, unk_c) for c in t][:word_size] for t in mtokens]

    baidx = [0 if i != ba else 1 for i, t in enumerate(ctokens)]
    eaidx = [0 if i != ea else 1 for i, t in enumerate(ctokens)]

    if not is_test and sum(eaidx) == 0:
        raise ValueError('problem with input line:\n%s' % line)

    if is_test and misc.keys():
        misc['answer'] += [answer]
        misc['rawctx'] += [context]
        misc['ctoken'] += [ctokens]

    return ctokens, qtokens, atokens, cwids, qwids, awids, mwids, ccids, qcids, acids, mcids, baidx, eaidx


def tsv_to_ctf(f, g, vocab, chars, is_test):
    print("Known words: %d" % known)
    print("Vocab size: %d" % len(vocab))
    print("Char size: %d" % len(chars))
    for lineno, line in enumerate(f):
        ctokens, qtokens, atokens, cwids, qwids, awids, mwids, ccids, qcids, acids, mcids, baidx, eaidx = tsv_iter(line,
                                                                                                                   vocab,
                                                                                                                   chars,
                                                                                                                   is_test)

        for ctoken, qtoken, atoken, cwid, qwid, awid, mwid, ccid, qcid, acid, mcid, begin, end in zip_longest(
                ctokens, qtokens, atokens, cwids, qwids, awids, mwids, ccids, qcids, acids, mcids, baidx, eaidx):
            out = [str(lineno)]
            if ctoken is not None:
                out.append('|# %s' % pad_spec.format(ctoken.translate(sanitize)))
            if qtoken is not None:
                out.append('|# %s' % pad_spec.format(qtoken.translate(sanitize)))
            if atoken is not None:
                out.append('|# %s' % pad_spec.format(atoken.translate(sanitize)))
            if cwid is not None:
                out.append('|cw {}:{}'.format(cwid, 1))
            if qwid is not None:
                out.append('|qw {}:{}'.format(qwid, 1))
            if awid is not None:
                out.append('|aw {}:{}'.format(awid, 1))
            if mwid is not None:
                out.append('|mw {}:{}'.format(mwid, 1))
            if ccid is not None:
                outc = ' '.join(['%d' % c for c in ccid + [0] * max(word_size - len(ccid), 0)])
                out.append('|cc %s' % outc)
            if qcid is not None:
                outq = ' '.join(['%d' % c for c in qcid + [0] * max(word_size - len(qcid), 0)])
                out.append('|qc %s' % outq)
            if acid is not None:
                outa = ' '.join(['%d' % c for c in acid + [0] * max(word_size - len(acid), 0)])
                out.append('|ac %s' % outa)
            if mcid is not None:
                outm = ' '.join(['%d' % c for c in mcid + [0] * max(word_size - len(mcid), 0)])
                out.append('|mc %s' % outm)
            if begin is not None:
                out.append('|ab %3d' % begin)
            if end is not None:
                out.append('|ae %3d' % end)
            g.write('\t'.join(out))
            g.write('\n')


if __name__ == '__main__':
    try:
        known, vocab, chars, npglove_matrix = pickle.load(open(vocab_map_file, 'rb'))
    except:
        known, vocab, chars = populate_dicts(tsvs)
        vocab_dim = len(vocab)
        npglove_matrix = np.zeros((vocab_dim, emb_dim), dtype=np.float32)
        with open(glove_file, 'r', encoding='utf-8') as file:
            for line in file:
                parts = line.split()
                word = parts[0].lower()
                if word in vocab:
                    npglove_matrix[vocab[word], :] = np.asarray([float(p) for p in parts[1:]])

        npglove_matrix[known:, :] = 2 * np.random.rand(vocab_dim - known, emb_dim) - np.ones(
            (vocab_dim - known, emb_dim), dtype=np.float32)

        f = open(vocab_map_file, 'wb')
        pickle.dump((known, vocab, chars, npglove_matrix), f)
        f.close()

    for tsv in tsvs:
        tsv_name = os.path.join('./data', tsv)
        with open('%s.tsv' % tsv_name, 'r', encoding='utf-8') as f:
            with open('%s.ctf' % tsv_name, 'w', encoding='utf-8') as g:
                tsv_to_ctf(f, g, vocab, chars, tsv == 'test')