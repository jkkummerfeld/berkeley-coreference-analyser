#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: set ts=2 sw=2 noet:

import sys, os
import pstree, treebanks, head_finder, render_tree
from collections import defaultdict
from StringIO import StringIO
import re
import glob, fnmatch

def read_conll_parses(lines):
	in_file = StringIO(''.join(lines))
	return treebanks.read_trees(in_file, treebanks.conll_read_tree)

def read_conll_text(lines):
	text = [[]]
	for line in lines:
		fields = line.strip().split()
		if len(fields) == 0:
			text.append([])
		else:
			text[-1].append(fields[3])
	if len(text[-1]) == 0:
		text.pop()
	return text

def read_conll_ner(lines):
	info = {}
	word = 0
	sentence = 0
	cur = []
	for line in lines:
		fields = line.strip().split()
		if len(fields) >= 11:
			ner_info = fields[10]
			if '(' in ner_info and '*' in ner_info:
				cur.append((ner_info[1:-1], sentence, word))
			elif '(' in ner_info and ')' in ner_info:
				info[sentence, word, word +1] = ner_info[1:-1]
			elif ')' in ner_info and '*' in ner_info:
				start = cur.pop()
				if sentence != start[1]:
					print >> sys.stderr, "Something mucked up", sentence, word, start
				info[sentence, start[2], word +1] = start[0]
		word += 1
		if len(fields) == 0:
			sentence += 1
			word = 0
	return info

def read_conll_coref(lines):
	# Assumes:
	#  - Reading a single part
	#  - If duplicate mentions occur, use the first
	regex = "([(][0-9]*[)])|([(][0-9]*)|([0-9]*[)])|([|])"
	mentions = {} # (sentence, start, end+1) -> ID
	clusters = defaultdict(lambda: []) # ID -> list of (sentence, start, end+1)s
	unmatched_mentions = defaultdict(lambda: [])

	sentence = 0
	word = 0
	line_no = 0
	for line in lines:
		line_no += 1
		if len(line) > 0 and line[0] =='#':
			continue
		line = line.strip()
		if len(line) == 0:
			sentence += 1
			word = 0
			unmatched_mentions = defaultdict(lambda: [])
			continue
		fields = line.strip().split()
		for triple in re.findall(regex, fields[-1]):
			if triple[1] != '':
				val = int(triple[1][1:])
				unmatched_mentions[(sentence, val)].append(word)
			elif triple[0] != '' or triple[2] != '':
				start = word
				val = -1
				if triple[0] != '':
					val = int(triple[0][1:-1])
				else:
					val = int(triple[2][:-1])
					if (sentence, val) not in unmatched_mentions:
###						print ''.join(lines[:20])
###						print triple
###						print fields
###						print line
###						print line_no, len(lines)
###						raise Exception("Ending mention with no start: " + str(val))
						print >> sys.stderr, "Ignoring a mention with no start", str(val), line.strip(), line_no
						continue
					if len(unmatched_mentions[(sentence, val)]) == 0:
						print >> sys.stderr, "No other start available", str(val), line.strip(), line_no
						continue
					start = unmatched_mentions[(sentence, val)].pop()
				end = word + 1
				if (sentence, start, end) in mentions:
					print >> sys.stderr, "Duplicate mention", sentence, start, end, val, mentions[sentence, start, end]
				else:
					mentions[sentence, start, end] = val
					clusters[val].append((sentence, start, end))
		word += 1
	for key in unmatched_mentions:
		if len(unmatched_mentions[key]) > 0:
			print >> sys.stderr, "Mention started, but did not end ", str(unmatched_mentions[key])
###			raise Exception("Mention started, but did not end " + str(unmatched_mentions[key]))
	return mentions, clusters

def read_stanford_coref(filename, gold_text):
	'''Example (most of the file clipped):
    <coreference>
      <coreference>
        <mention representative="true">
          <sentence>1</sentence>
          <start>13</start>
          <end>15</end>
          <head>14</head>
        </mention>
        <mention>
          <sentence>15</sentence>
          <start>43</start>
          <end>45</end>
          <head>44</head>
        </mention>
      </coreference>
      <coreference>
        <mention representative="true">
          <sentence>1</sentence>
          <start>16</start>
          <end>17</end>
          <head>16</head>
        </mention>
        <mention>
          <sentence>9</sentence>
          <start>1</start>
          <end>2</end>
          <head>1</head>
        </mention>
      </coreference>
    </coreference>'''
	mentions = {} # (sentence, start, end+1) -> ID
	clusters = defaultdict(lambda: []) # ID -> list of (sentence, start, end+1)s
	text = [[]]
	sentence = None
	start = None
	end = None
	cluster = 0
	for line in open(filename):
		if '<word>' in line:
			text[-1].append(line.split('<word>')[1].split('</word>')[0])
		elif '</sentence>' in line:
			if '<sentence>' not in line:
				text.append([])
			else:
				sentence = int(line.split('<sentence>')[1].split('</sentence>')[0]) - 1
		elif '<start>' in line:
			start = int(line.split('<start>')[1].split('</start>')[0]) - 1
		elif '<end>' in line:
			end = int(line.split('<end>')[1].split('</end>')[0]) - 1
		elif '</coreference>' in line:
			cluster += 1
		elif '</mention>' in line:
			if (sentence, start, end) in mentions:
				print "Duplicate mention:", cluster, mentions[sentence, start, end]
			else:
				mentions[sentence, start, end] = cluster
				clusters[cluster].append((sentence, start, end))
	return {'clusters': clusters, 'mentions': mentions, 'text': text}

def read_uiuc_coref(filename, gold_text):
	'''Example:
	After *Mingxia Fu*_5 won **the champion for the *women*_8 platform*_6 diving*_4 , *the coach of *the *Soviet Union*_3 team*_0*_1 congratulated *her*_1 warmly . Photo taken by **Xinhua News Agency*_2 reporter*_7 , *Zhishan Cheng*_7 .
	Note that occasionally words have *s, e.g. *when*, in which case this hits issues without manual editing of the text.
	'''
	mentions = {} # (sentence, start, end+1) -> ID
	clusters = defaultdict(lambda: []) # ID -> list of (sentence, start, end+1)s
	unmatched_mentions = []
	text = [[]]
	sentence = 0
	word = 0
	prev = ['', '']
	last_sentence = []
	for line in open(filename):
		for token in line.split():
			# Case of a single *
			if re.match('^[*]+$', token) is None:
				# Starts
				for char in token:
					if char == '*':
						unmatched_mentions.append((word, sentence))
					else:
						break
				
				# Ends
				regex = '[*][_][0-9]+'
				for end in re.findall(regex, token):
					cluster = int(end[2:])
					end = word + 1
					start, msentence = unmatched_mentions.pop()
					if msentence != sentence:
						end = len(gold_text[msentence])
					if (msentence, start, end) in mentions:
						print "Duplicate mention:", cluster, mentions[msentence, start, end]
					else:
						mentions[msentence, start, end] = cluster
						clusters[cluster].append((msentence, start, end))

				# Strip down to just the token
				while token[0] == '*':
					token = token[1:]
				regex = '[*][_][0-9]+'
				token = re.split(regex, token)[0]

			# Deal with token splitting
			if token == gold_text[sentence][word]:
				prev = ['', '']
				word += 1
				text[-1].append(token)
			else:
				if len(prev[0]) == 0:
					prev[0] = gold_text[sentence][word]
					prev[1] = token
					text[-1].append(token)
				elif prev[1] + token == prev[0]:
					if len(text[-1]) == 0:
						text[-2][-1] = prev[0]
					else:
						text[-1][-1] = prev[0]
					word += 1
					prev = ['', '']
				else:
					prev[1] += token
			if word == len(gold_text[sentence]):
				word = 0
				sentence += 1
				text.append([])
	if len(text[-1]) == 0:
		text.pop()
	return {'clusters': clusters, 'mentions': mentions, 'text': text}

def read_cherrypicker_coref(filename, gold_text):
	'''Example:
	<COREF ID="8" REF="7">Giant</COREF> agreed last month to purchase the <COREF ID="3" REF="2">carrier</COREF> .
	Note, some manual editing was also required to deal with '+'s being split off.'''
	regex = '(<COREF [^>]*>)|(</COREF> *)|( *[^< ][^< ]* *)'
	mentions = {} # (sentence, start, end+1) -> ID
	clusters = defaultdict(lambda: []) # ID -> list of (sentence, start, end+1)s
	unmatched_mentions = []
	text = [[]]
	sentence = 0
	word = 0
	prev = ['', '']
	mapping = {}
	word_convert = {'learnt': 'learned', 'learned': 'learnt'}
	for line in open(filename):
		for coref_start, coref_end, token in re.findall(regex, line.strip()):
			if token != '':
###				print token, gold_text[sentence][word]
				token = token.strip()
				allowed = token == gold_text[sentence][word]
				allowed = allowed or token in '{}[]()'
				allowed = allowed or (token in word_convert and word_convert[token] == gold_text[sentence][word])
				allowed = allowed or '/'.join(token.split('_')) == gold_text[sentence][word]
				if allowed:
					prev = ['', '']
					word += 1
					text[-1].append(token)
				else:
					if len(prev[0]) == 0:
						prev[0] = gold_text[sentence][word]
						prev[1] = token
						text[-1].append(token)
###						print prev, token, filename
					elif prev[1] + token == prev[0] or '/'.join((prev[1] + token).split('_')) == prev[0]:
						if len(text[-1]) == 0:
							text[-2][-1] = prev[0]
						else:
							text[-1][-1] = prev[0]
						word += 1
						prev = ['', '']
###						print prev, token, filename
					else:
###						print prev, token, filename
						prev[1] += token

				if word == len(gold_text[sentence]):
					word = 0
					sentence += 1
					text.append([])
			elif coref_start != '':
				mention_id = int(coref_start.split('ID="')[1].split('"')[0])
				if 'REF=' in coref_start:
					cluster = mapping[int(coref_start.split('REF="')[1].split('"')[0])]
				else:
					cluster = mention_id
				mapping[mention_id] = cluster
				unmatched_mentions.append((cluster, sentence, word))
			elif coref_end != '':
				cluster, msentence, start = unmatched_mentions.pop()
				end = word
				if msentence != sentence:
					end = len(gold_text[msentence])
				elif end == start and len(prev[0]) > 0:
					end += 1
				mentions[msentence, start, end] = cluster
				clusters[cluster].append((msentence, start, end))
	if len(text[-1]) == 0:
		text.pop()
	return {'clusters': clusters, 'mentions': mentions, 'text': text}

def read_bart_coref(filename, gold_text):
	'''Example output:
	<s>
	<coref set-id="set_24">
	<w pos="prp">It</w>
	</coref>
	<w pos="md">must</w>
	<w pos="rb">also</w>
	<w pos="vb">evaluate</w>
	<coref set-id="set_0">
	<w pos="dt">the</w>
	<w pos="jj">real</w>
	<w pos=":">-</w>
	<coref set-id="set_1">
	<w pos="nn">estate</w>
	</coref>
	<w pos="nn">market</w>
	</coref>
	<w pos="in">in</w>
	<w pos="dt">the</w>
	<w pos="vbn">chosen</w>
	<w pos="nn">location</w>
	<w pos="in">from</w>
	<w pos="dt">a</w>
	<w pos="jj">new</w>
	<w pos="nn">perspective</w>
	<w pos=".">.</w>
	</s>'''
	regex = '(<[^>]*>)|([^<]* *)'
	text = [[]]
	mentions = {} # (sentence, start, end+1) -> ID
	clusters = defaultdict(lambda: []) # ID -> list of (sentence, start, end+1)s
	unmatched_mentions = []
	sentence = 0
	word = 0
	prev = []
	for line in open(filename):
		for tag, token in re.findall(regex, line.strip()):
			if token != '':
				if '&amp;' in token:
					token = '&'.join(token.split('&amp;'))
				if '&middot;' in token:
					pass
				elif token != gold_text[sentence][word]:
###					if len(prev) > 2:
###						print gold_text[sentence][word], token, ''.join(prev), filename
					if len(prev) == 0:
						prev.append(token)
						token = None
					else:
						if ''.join(prev + [token]) == gold_text[sentence][word]:
							token = ''.join(prev + [token])
							prev = []
						else:
							prev.append(token)
							token = None
				if token is not None:
					text[-1].append(token)
					word += 1
					if word == len(gold_text[sentence]):
						word = 0
						sentence += 1
						text.append([])
			elif '<coref' in tag:
				cluster = int(tag.split('set_')[1].split('"')[0])
				unmatched_mentions.append((cluster, sentence, word))
			elif tag == '</coref>':
				cluster, msentence, start = unmatched_mentions.pop()
				end = word
				if sentence != msentence:
					end = len(text[msentence])
				if len(prev) > 0:
					end += 1
				mentions[msentence, start, end] = cluster
				clusters[cluster].append((msentence, start, end))
	if len(text[-1]) == 0:
		text.pop()
	return {'clusters': clusters, 'mentions': mentions, 'text': text}

def read_reconcile_coref(filename, gold_text):
	'''Example output:
	<NP NO="14" CorefID="11">It</NP> must also evaluate <NP NO="15" CorefID="26">the real - estate market</NP> in <NP      NO="16" CorefID="16">the chosen location from <NP NO="17" CorefID="17">a new perspective</NP></NP> .'''
	regex = '(<[^>]*>)|( *[^< ][^< ]* *)'
	text = [[]]
	mentions = {} # (sentence, start, end+1) -> ID
	clusters = defaultdict(lambda: []) # ID -> list of (sentence, start, end+1)s
	unmatched_mentions = []
	sentence = 0
	word = 0
	prev = []
	for line in open(filename):
		for tag, token in re.findall(regex, line.strip()):
			if token != '':
				token = token.strip()
				if token != gold_text[sentence][word]:
###					if len(prev) > 2:
###						print "'%s' '%s'" % (token, gold_text[sentence][word])
###						print ''.join(prev), sentence, word, filename
					if len(prev) == 0:
						prev.append(token)
						token = None
					else:
						if ''.join(prev + [token]) == gold_text[sentence][word]:
							token = ''.join(prev + [token])
							prev = []
						else:
							prev.append(token)
							token = None
				if token is not None:
					text[-1].append(token)
					word += 1
					if word == len(gold_text[sentence]):
						word = 0
						sentence += 1
						text.append([])
			elif '<NP' in tag:
				cluster = int(tag.split('CorefID="')[1].split('"')[0])
				unmatched_mentions.append((cluster, sentence, word))
			elif tag == '</NP>':
				cluster, msentence, start = unmatched_mentions.pop()
				end = word
				if sentence != msentence:
					end = len(text[msentence])
				elif len(prev) > 0:
					end += 1
				mentions[msentence, start, end] = cluster
				clusters[cluster].append((msentence, start, end))
	if len(text[-1]) == 0:
		text.pop()
	return {'clusters': clusters, 'mentions': mentions, 'text': text}

def read_conll_doc(filename, ans=None, rtext=True, rparses=True, rheads=True, rclusters=True, rner=True):
	# Read entire file, inserting into a dictionary:
	#  key - the #begin <blah> info
	#  value - a dict, one entry per part, each entry contains:
	#     - text
	#     - parses
	#     - heads
	#     - coreference clusters
	if ans is None:
		ans = defaultdict(lambda: {})
	cur = []
	keys = None
	for line in open(filename):
		if len(line) > 0 and line.startswith('#begin') or line.startswith('#end'):
			if 'begin' in line:
				desc = line.split()
				location = desc[2].strip('();')
				keys = (location, desc[-1])
			if len(cur) > 0:
				if keys is None:
					print >> sys.stderr, "Error reading conll file - invalid #begin statemen\n", line
				else:
					info = {}
					if rtext:
						info['text'] = read_conll_text(cur)
					if rparses:
						info['parses'] = read_conll_parses(cur)
						if rheads:
							info['heads'] = [head_finder.collins_find_heads(parse) for parse in info['parses']]
					if rclusters:
						info['mentions'], info['clusters'] = read_conll_coref(cur)
					if rner:
						info['ner'] = read_conll_ner(cur)
					ans[keys[0]][keys[1]] = info
					keys = None
			cur = []
		else:
			cur.append(line)
	return ans

def read_conll_gold_files(dir_prefix):
	ans = defaultdict(lambda: {})
	query = os.path.join(dir_prefix, '*/*/*/*gold*conll')
	for filename in glob.glob(query):
		read_conll_doc(filename, ans)
	return ans

def read_conll_coref_system_output(filename, ans=None):
	return read_conll_doc(filename, ans, False, False, False, True)

def read_conll_matching_file(dir_prefix, filename, ans=None):
	if ans is None:
		ans = defaultdict(lambda: {})
	query = os.path.join(dir_prefix, filename + '*gold*conll')
	filenames = glob.glob(query)
	if len(filenames) == 1:
		read_conll_doc(filenames[0], ans)
	else:
		print >> sys.stderr, "Reading matching doc failed for %s/%s as %d files were found." % (dir_prefix, filename, len(filenames))
	return ans

def read_conll_matching_files(conll_docs, dir_prefix):
	# Read the corresponding file under dir_prefix
	ans = None
	for filename in conll_docs:
		if "tc/ch/00/ch" in filename and '9' not in filename:
			val = int(filename.split('_')[-1]) * 10 - 1
			filename = "tc/ch/00/ch_%04d" % val
		ans = read_conll_matching_file(dir_prefix, filename, ans)
	return ans

def read_conll_all(dir_prefix, suffix="auto_conll"):
	ans = None
	for root, dirnames, filenames in os.walk(dir_prefix):
		for filename in fnmatch.filter(filenames, '*' + suffix):
			ans = read_conll_doc(os.path.join(root, filename), ans)
	return ans

def read_conll_scorer_output(text):
	'''
	
	>>> text = """version: 1.07
	... 
	... METRIC muc:
	... 
	... ====== TOTALS =======
	... Identification of Mentions: Recall: (10049 / 14291) 70.31%	Precision: (10049 / 12968) 77.49%	F1: 73.72%
	... --------------------------------------------------------------------------
	... Coreference: Recall: (6891 / 10539) 65.38%	Precision: (6891 / 9671) 71.25%	F1: 68.19%
	... --------------------------------------------------------------------------
	... 
	... METRIC bcub:
	... 
	... ====== TOTALS =======
	... Identification of Mentions: Recall: (10049 / 14291) 70.31%	Precision: (10049 / 12968) 77.49%	F1: 73.72%
	... --------------------------------------------------------------------------
	... Coreference: Recall: (9445.16162068698 / 14291) 66.09%	Precision: (13366.8103055043 / 17210) 77.66%	F1: 71.41%
	... --------------------------------------------------------------------------
	... 
	... METRIC ceafm:
	... 
	... ====== TOTALS =======
	... Identification of Mentions: Recall: (10049 / 14291) 70.31%	Precision: (10049 / 12968) 77.49%	F1: 73.72%
	... --------------------------------------------------------------------------
	... Coreference: Recall: (10046 / 14291) 70.29%	Precision: (11103 / 17210) 64.51%	F1: 67.28%
	... --------------------------------------------------------------------------
	... 
	... METRIC ceafe:
	... 
	... ====== TOTALS =======
	... Identification of Mentions: Recall: (10049 / 14291) 70.31%	Precision: (10049 / 12968) 77.49%	F1: 73.72%
	... --------------------------------------------------------------------------
	... Coreference: Recall: (3490.14880751078 / 6671) 52.31%	Precision: (3490.14880751078 / 7539) 46.29%	F1: 49.12%
	... --------------------------------------------------------------------------
	... 
	... METRIC blanc:
	... 
	... ====== TOTALS =======
	... Identification of Mentions: Recall: (10049 / 14291) 70.31%	Precision: (10049 / 12968) 77.49%	F1: 73.72%
	... --------------------------------------------------------------------------
	... 
	... Coreference:
	... Coreference links: Recall: (33214 / 54427) 61.02%	Precision: (33214 / 51699) 64.24%	F1: 62.59%
	... --------------------------------------------------------------------------
	... Non-coreference links: Recall: (785075 / 803560) 97.69%	Precision: (785075 / 806288) 97.36%	F1: 97.53%
	... --------------------------------------------------------------------------
	... BLANC: Recall: (0.793622353566206 / 1) 79.36%	Precision: (0.80807005307929 / 1) 80.8%	F1: 80.06%
	... --------------------------------------------------------------------------"""
	>>> results = read_conll_scorer_output(text)
	>>> for metric in results:
	...   print metric, results[metric]
	bcub [77.66, 66.09, 71.41]
	ceafm [64.51, 70.29, 67.28]
	muc [71.25, 65.38, 68.19]
	mentions [77.49, 70.31, 73.72]
	ceafe [46.29, 52.31, 49.12]
	blanc [80.8, 79.36, 80.06]
	'''
	metric = None
	totals = False
	results = defaultdict(lambda: [])
	for line in text.split('\n'):
		fields = line.strip().split()
		if 'METRIC' in line:
			metric = line.strip().split()[1][:-1]
		elif 'TOTALS' in line:
			totals = True
		elif 'Identification of Mentions' in line and totals:
			recall = float(fields[4][1:]) / float(fields[6][:-1])
			precision = float(fields[9][1:]) / float(fields[11][:-1])
			fscore = 0.0
			if precision + recall > 0:
				fscore = 2 * precision * recall / (precision + recall)
			results['mentions'] = [precision, recall, fscore]
		elif totals and (('Coreference' in line and metric != 'blanc') or 'BLANC:' in line):
			recall = float(fields[2][1:]) / float(fields[4][:-1])
			precision = float(fields[7][1:]) / float(fields[9][:-1])
			fscore = 0.0
			if precision + recall > 0:
				fscore = 2 * precision * recall / (precision + recall)
			results[metric] = [precision, recall, fscore]
		elif line.strip() == '' and totals:
			if len(results[metric]) == 3:
				totals = False
	if 'ceafe' in results and 'muc' in results and 'bcub' in results:
		results['conll'] = [0, 0, 0]
		for metric in ['muc', 'bcub', 'ceafe']:
			for i in xrange(3):
				results['conll'][i] += results[metric][i] / 3.0
	return results

###if __name__ == "__main__":
###	print "Running doctest"
###	import doctest
###	doctest.testmod()

