#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: set ts=2 sw=2 noet:

import sys, string
import render_tree, coreference_reading, head_finder, coreference, init

from collections import defaultdict

# TODO:
# Add ordering information for the context printing
# Add the ability to print without the newlines (or just return strings?)
# Add the option to print a cluster error group with missing mentions as singletons throughout the rest

CONTEXT = 40
ANSI_WHITE = 15
ANSI_YELLOW = 3
ANSI_RED = 1

def match_boundaries(gold_mention_set, auto_mention_set, auto_mentions, auto_clusters, auto_cluster_set, text, parses, heads):
	# Apply changes for cases where the difference is only leading or trailing punctuation
	mapping = {}
	used_gold = set()
	unique_to_gold = gold_mention_set.difference(auto_mention_set)
	unique_to_auto =  auto_mention_set.difference(gold_mention_set)
	for amention in unique_to_auto:
		sentence, astart, aend = amention
		while (aend - astart > 1 and
		       (text[sentence][astart] == "the" or
		       (len(text[sentence][astart]) == 1 and
		       text[sentence][astart][0] not in string.letters))):
			astart += 1
		while (aend - astart > 1 and
		       (text[sentence][aend - 1] == "'s" or
		       (len(text[sentence][aend - 1]) == 1 and
		       text[sentence][aend - 1][0] not in string.letters))):
			aend -= 1
		for gmention in unique_to_gold:
			gsentence, gstart, gend = gmention
			if sentence != gsentence or gmention in used_gold:
				continue
			while (gend - gstart > 1 and
			       (text[sentence][gstart] == "the" or
			       (len(text[sentence][gstart]) == 1 and
			       text[sentence][gstart][0] not in string.letters))):
				gstart += 1
			while (gend - gstart > 1 and
			       (text[sentence][gend - 1] == "'s" or
			       (len(text[sentence][gend - 1]) == 1 and
			       text[sentence][gend - 1][0] not in string.letters))):
				gend -= 1
			if astart == gstart and aend == gend:
				mapping[amention] = gmention
				used_gold.add(gmention)
	# Apply mapping to create new auto_mention_set
	for mention in mapping:
		auto_mention_set.remove(mention)
		auto_mention_set.add(mapping[mention])
		cluster_id = auto_mentions.pop(mention)
		auto_mentions[mapping[mention]] = cluster_id
		auto_clusters[cluster_id].remove(mention)
		auto_clusters[cluster_id].append(mapping[mention])
		to_remove = None
		for cluster in auto_cluster_set:
			if mention in cluster:
				to_remove = cluster
		auto_cluster_set.remove(to_remove)
		ncluster = []
		for mention2 in to_remove:
			if mention2 == mention:
				mention2 = mapping[mention]
			ncluster.append(mention2)
		ncluster = tuple(ncluster)
		auto_cluster_set.add(ncluster)

	# Create a mapping based on heads
	head_dict = defaultdict(lambda: {'auto': [], 'gold': []})
	for mention in auto_mention_set.difference(gold_mention_set):
		sentence, start, end = mention
		head = coreference.mention_head(mention, text, parses, heads, default_last=True)
		# This will default to last word if the mention is not a constituent, is
		# there an alternative?
		if head is not None:
			head = (mention[0], head[0])
			head_dict[head]['auto'].append(mention)
	for mention in gold_mention_set.difference(auto_mention_set):
		sentence, start, end = mention
		head = coreference.mention_head(mention, text, parses, heads, default_last=True)
		if head is not None:
			head = (mention[0], head[0])
			head_dict[head]['gold'].append(mention)

	mapping = {}
	for head in head_dict:
		amentions = head_dict[head]['auto']
		gmentions = head_dict[head]['gold']
		if len(amentions) == 1 and len(gmentions) == 1:
			mapping[amentions[0]] = gmentions[0]

	# Apply mapping to create new auto_mention_set
	for mention in mapping:
		auto_mention_set.remove(mention)
		auto_mention_set.add(mapping[mention])
		cluster_id = auto_mentions.pop(mention)
		auto_mentions[mapping[mention]] = cluster_id
		auto_clusters[cluster_id].remove(mention)
		auto_clusters[cluster_id].append(mapping[mention])
		to_remove = None
		for cluster in auto_cluster_set:
			if mention in cluster:
				to_remove = cluster
		auto_cluster_set.remove(to_remove)
		ncluster = []
		for mention2 in to_remove:
			if mention2 == mention:
				mention2 = mapping[mention]
			ncluster.append(mention2)
		ncluster = tuple(ncluster)
		auto_cluster_set.add(ncluster)

def print_conll_style_part(out, text, mentions, doc, part):
	doc_str = doc
	if "tc/ch/00/ch" in doc and '9' not in doc:
		val = int(doc.split('_')[-1]) * 10 - 1
		doc_str = "tc/ch/00/ch_%04d" % val
	print >> out, "#begin document (%s); part %s" % (doc_str, part)
	starts = defaultdict(lambda: [])
	ends = defaultdict(lambda: [])
	singles = defaultdict(lambda: [])
	for mention in mentions:
		cluster_id = mentions[mention]
		if mention[2] - mention[1] == 1:
			singles[mention[0], mention[1]].append(cluster_id)
		else:
			starts[mention[0], mention[1]].append(cluster_id)
			ends[mention[0], mention[2] - 1].append(cluster_id)

	for i in xrange(len(text)):
		for j in xrange(len(text[i])):
			coref = []
			if (i, j) in starts:
				for cluster_id in starts[i, j]:
					coref.append('(' + str(cluster_id))
			if (i, j) in singles:
				for cluster_id in singles[i, j]:
					coref.append('(' + str(cluster_id) + ')')
			if (i, j) in ends:
				for cluster_id in ends[i, j]:
					coref.append(str(cluster_id) + ')')
			if len(coref) == 0:
				coref = '-'
			else:
				coref = '|'.join(coref)
			print >> out, "%s\t%d\t%d\t%s\t%s" % (doc_str, int(part), j, text[i][j], coref)
		print >> out

	print >> out, "#end document"

def print_conll_style(data, gold, out):
	for doc in data:
		for part in data[doc]:
			print_conll_style_part(out, gold[doc][part]['text'], data[doc][part]['mentions'], doc, part)

def mention_text(text, mention, parses=None, heads=None, colour=None):
	sentence, start, end = mention
	head = None
	if parses is not None and heads is not None and end - start > 1:
		node = parses[sentence].get_nodes('lowest', start, end)
		if node is not None:
			head = head_finder.get_head(heads[sentence], node)
	ans = []
	for i in xrange(start, end):
		ans.append(text[sentence][i])
		if head is not None:
			if head[0][0] == i:
				ans[-1] = "\033[4m" + ans[-1] + "\033[0m"
	ans = ' '.join(ans)
	if colour is not None:
		ans = ans.split("\033[0m")
		if len(ans) == 1 or len(ans[1]) == 0:
			ans = colour + ans[0] + "\033[0m"
		else:
			ans = colour + ans[0] + "\033[0m" + colour + ans[1] + "\033[0m"
	return ans

def mention_context(text, mention):
	sentence, start, end = mention
	ans = ['', '']
	cur = [sentence, start - 1]
	while True:
		if cur[1] < 0:
			if cur[0] == 0:
				break
			cur[0] -= 1
			cur[1] = len(text[cur[0]]) - 1
		word = text[cur[0]][cur[1]]
		if len(ans[0]) == 0:
			ans[0] = word
		elif len(ans[0]) + len(word) < CONTEXT - 1:
			ans[0] = word + ' ' + ans[0]
		else:
			break
		cur[1] -= 1

	cur = [sentence, end]
	while True:
		if cur[1] == len(text[cur[0]]):
			if cur[0] == len(text) - 1:
				break
			cur[0] += 1
			cur[1] = 0
		word = text[cur[0]][cur[1]]
		if len(ans[1]) == 0:
			ans[1] = word
		elif len(ans[1]) + len(word) < CONTEXT - 1:
			ans[1] = ans[1] + ' ' + word
		else:
			break
		cur[1] += 1
	return ans

def print_headless_mentions(out, parses, heads, mentions):
	for mention in mentions:
		sentence, start, end = mention
		if end - start > 1:
			node = parses[sentence].get_nodes('lowest', start, end)
			if node is None:
				print >> out, mention_text(text, mention)
				print >> out, render_tree.text_tree(parses[sentence], False)

def print_mention(out, with_context, gold_parses, gold_heads, text, mention, colour=None, extra=False, return_str=False):
	pre_context, post_context = mention_context(text, mention)
	if extra:
		colour = ANSI_RED
	if colour is None:
		if with_context:
			colour = ANSI_YELLOW
		else:
			colour = ANSI_WHITE
	mtext = mention_text(text, mention, gold_parses, gold_heads, "\033[38;5;%dm" % colour)

	to_print = "{:<15}".format(str(mention))
	if with_context:
		to_print += '%s %s  %s  %s' % (' ' * (CONTEXT - len(pre_context)), pre_context, mtext, post_context)
	else:
		if extra:
			to_print += 'Extra:  '
		to_print += mtext

	if return_str:
		return to_print
	else:
		print >> out, to_print

def print_cluster_errors(groups, out_errors, out_context, text, gold_parses, gold_heads, auto_clusters, gold_clusters, gold_mentions):
	'''Mentions are printed to show both system and gold clusters:
 - Mentions are placed in groups that correspond to the system cluster
 - Colour is used to indicate the gold clusters, with red indicating spurious mentions
For each mention the tuple of numbers indicates (sentence, start word, end word
+ 1).  Colours reset after each dsahed line.'''
	mixed_groups = []
	for i in xrange(len(groups)):
		auto, gold = groups[i]
		if len(auto) == 0:
			# All missing
			continue
		if len(gold) == 0:
			# All extra
			continue
		auto_count = len(auto)
		mention_count = sum([len(c) for c in auto])
		mention_count += sum([len(c) for c in gold])
		earliest_mention = None
		if len(auto) > 0:
			earlisest_mention = min([min(c) for c in auto])
		if len(gold) > 0:
			earliest_gold = min([min(c) for c in gold])
			if earliest_mention is None or earliest_gold < earliest_mention:
				earliest_mention = earliest_gold
		mixed_groups.append((auto_count, mention_count, earliest_mention, i))
	mixed_groups.sort(reverse=True)
	mixed_groups = [groups[gset[-1]] for gset in mixed_groups]
	covered = set()
	for group in mixed_groups:
		print_cluster_error_group(group, out_errors, text, gold_parses, gold_heads, gold_mentions)
		print_cluster_error_group(group, out_context, text, gold_parses, gold_heads, gold_mentions, True)
		print >> out_errors
		print >> out_context
		print >> out_errors, '-' * 60
		print >> out_context, '-' * 60
		print >> out_errors
		print >> out_context
		for part in group:
			for entity in part:
				covered.update(entity)
	return covered

def print_cluster_error_group(group, out, text, gold_parses, gold_heads, gold_mentions, with_context=False, colour_map=None):
	auto, gold = group
	if colour_map is None:
		colour_map = {}
	next_colour = 3
	# Check if all in the same gold entity
	auto_count = len(auto)
	gold_count = len(gold)
	all_gold = set()
	for cluster in gold:
		all_gold.update(cluster)
	all_auto = set()
	for cluster in auto:
		all_auto.update(cluster)
	spurious = all_auto.difference(all_gold)
	missing = all_gold.difference(all_auto)

	if auto_count == 1 and gold_count == 1 and len(spurious) == 0 and len(missing) == 0:
		# Perfect match
		for cluster in auto:
			sorted_cluster = list(cluster)
			sorted_cluster.sort()
			for mention in sorted_cluster:
				print_mention(out, with_context, gold_parses, gold_heads, text, mention)
	elif auto_count == 1 and gold_count == 1:
		# Only one eneity present, so print all white (except extra)
		for cluster in auto:
			sorted_cluster = list(cluster)
			sorted_cluster.sort()
			for mention in sorted_cluster:
				if mention not in gold_mentions:
					print_mention(out, with_context, gold_parses, gold_heads, text, mention, extra=True)
				else:
					print_mention(out, with_context, gold_parses, gold_heads, text, mention)
					colour_map[gold_mentions[mention]] = ANSI_WHITE
	else:
		sorted_clusters = [(min(c), c) for c in auto]
		sorted_clusters.sort()
		first = True
		for earliest, cluster in sorted_clusters:
			if first:
				first = False
			else:
				print >> out
			sorted_cluster = list(cluster)
			sorted_cluster.sort()
			for mention in sorted_cluster:
				if mention not in gold_mentions:
					print_mention(out, with_context, gold_parses, gold_heads, text, mention, extra=True)
				else:
					if gold_mentions[mention] not in colour_map:
						colour_map[gold_mentions[mention]] = next_colour
						next_colour += 1
						# Skip shades close to white, red and black
						while next_colour in [7, 9, 15, 16]:
							next_colour += 1
					colour = colour_map[gold_mentions[mention]]
					print_mention(out, with_context, gold_parses, gold_heads, text, mention, colour)

	if len(missing) > 0:
		print >> out
		print >> out, "Missing:"
		for cluster in gold:
			sorted_cluster = list(cluster)
			sorted_cluster.sort()
			for mention in sorted_cluster:
				if mention in missing:
					if auto_count <= 1 and gold_count == 1:
						print_mention(out, with_context, gold_parses, gold_heads, text, mention)
					else:
						print_mention(out, with_context, gold_parses, gold_heads, text, mention, colour_map[gold_mentions[mention]])
	return colour_map

def print_cluster_missing(out_errors, out_context, out, text, gold_cluster_set, covered, gold_parses, gold_heads):
	'''Clusters that consist entirely of mentions that are not present in the
system output.'''
	print >> out_errors, "Missing:"
	print >> out_context, "Missing:"
	for entity in gold_cluster_set:
		printed = 0
		for mention in entity:
			if mention not in covered:
				print_mention(out, False, gold_parses, gold_heads, text, mention)
				print_mention(out_errors, False, gold_parses, gold_heads, text, mention)
				print_mention(out_context, True, gold_parses, gold_heads, text, mention)
				printed += 1
		if printed > 0 and len(entity) != printed:
			print >> sys.stderr, "Covered isn't being filled correctly (missing)", printed, len(entity)
			print >> sys.stderr, entity
			for mention in entity:
				if mention not in covered:
					print >> sys.stderr, mention
		if printed > 0:
			print >> out_errors
			print >> out_context
			print >> out

def print_cluster_extra(out_errors, out_context, out, text, auto_cluster_set, covered, gold_parses, gold_heads):
	'''Clusters that consist entirely of mentions that are not present in the
gold standard.'''
	print >> out_errors, "Extra:"
	print >> out_context, "Extra:"
	for entity in auto_cluster_set:
		printed = 0
		for mention in entity:
			if mention not in covered:
				print_mention(out, False, gold_parses, gold_heads, text, mention, extra=True)
				print_mention(out_errors, False, gold_parses, gold_heads, text, mention, extra=True)
				print_mention(out_context, True, gold_parses, gold_heads, text, mention, extra=True)
				printed += 1
		if printed > 0 and len(entity) != printed:
			print >> sys.stderr, "Covered isn't being filled correctly (extra)", printed, len(entity)
			print >> sys.stderr, entity
			for mention in entity:
				if mention not in covered:
					print >> sys.stderr, mention
		if printed > 0:
			print >> out_errors
			print >> out_context
			print >> out
	print >> out_errors, '-' * 60
	print >> out_context, '-' * 60
	print >> out_errors
	print >> out_context

def print_mention_list(out, gold_mentions, auto_mention_set, gold_parses, gold_heads, text):
	'''Mentions in each document:
 - Mentions that occur in both gold and system output are white
 - Mentions that appear only in the gold are blue
 - Mentions that appear only in the system output are red
For each mention the tuple of numbers indicates (sentence, start word, end word
+ 1), and the underlined word is the head of the mention (determined from the
gold parse tree).'''
	mentions = [(m, True) for m in gold_mentions]
	for mention in auto_mention_set:
		if mention not in gold_mentions:
			mentions.append((mention, False))
	mentions.sort()
	for mention in mentions:
		if not mention[1]:
			print_mention(out, False, gold_parses, gold_heads, text, mention[0], colour=ANSI_RED)
		elif mention[0] not in auto_mention_set:
			print_mention(out, False, gold_parses, gold_heads, text, mention[0], colour=4)
		else:
			print_mention(out, False, gold_parses, gold_heads, text, mention[0])

def print_mention_text(out, gold_mentions, auto_mention_set, gold_parses, gold_heads, text):
	'''Document text with both system and gold mentions marked:
 - Gold mentions are marked with '[ ... ]'
 - System mentions are marked with '( ... )'
 - Mentions that occur in both are marked with '{ ... }'
Colour is used to indicate missing and extra mentions.  Blue for missing, red
for extra, and purple where they overlap.'''

	mentions_by_sentence = defaultdict(lambda: [[], []])
	for mention in gold_mentions:
		mentions_by_sentence[mention[0]][0].append(mention)
	for mention in auto_mention_set:
		mentions_by_sentence[mention[0]][1].append(mention)
	
	# Maps from word locations to tuples of:
	# ( in missing mention , in extra mention , is a head , 
	#   [(is gold? , end)]
	#   [(is gold? , start)] )
	word_colours = {}
	heads = set()
	for mention in gold_mentions:
		node = gold_parses[mention[0]].get_nodes('lowest', mention[1], mention[2])
		if node is not None:
			head = head_finder.get_head(gold_heads[mention[0]], node)
			heads.add((mention[0], head[0][0]))
	for mention in auto_mention_set:
		node = gold_parses[mention[0]].get_nodes('lowest', mention[1], mention[2])
		if node is not None:
			head = head_finder.get_head(gold_heads[mention[0]], node)
			heads.add((mention[0], head[0][0]))

	words = defaultdict(lambda: defaultdict(lambda: [False, False]))
	for mention in gold_mentions:
		for i in xrange(mention[1], mention[2]):
			words[mention[0], i][mention][0] = True
	for mention in auto_mention_set:
		for i in xrange(mention[1], mention[2]):
			words[mention[0], i][mention][1] = True

	# Printing
	for sentence in xrange(len(text)):
		output = []
		for word in xrange(len(text[sentence])):
			text_word = text[sentence][word]
			if (sentence, word) in words:
				mention_dict = words[(sentence, word)]

				missing = set()
				for mention in mention_dict:
					if mention_dict[mention][0] and not mention_dict[mention][1]:
						missing.add(mention)
				extra = set()
				for mention in mention_dict:
					if not mention_dict[mention][0] and mention_dict[mention][1]:
						extra.add(mention)
				starts = []
				for mention in mention_dict:
					if mention[1] == word:
						starts.append((mention[2], mention_dict[mention], mention))
				starts.sort(reverse=True)
				ends = []
				for mention in mention_dict:
					if mention[2] - 1 == word:
						ends.append((mention[1], mention_dict[mention], mention))
				ends.sort(reverse=True)
				
				start = ''
				for mention in starts:
					character = ''
					if mention[1][0] and mention[1][1]:
						character = '{'
					elif mention[1][0]:
						character = '['
					elif mention[1][1]:
						character = '('
					inside_missing = False
					for emention in missing:
						if emention[1] <= mention[2][1] and mention[2][2] <= emention[2]:
							inside_missing = True
					inside_extra = False
					for emention in extra:
						if emention[1] <= mention[2][1] and mention[2][2] <= emention[2]:
							inside_extra = True
					colour = '15'
					if inside_missing and inside_extra:
						colour = '5'
					elif inside_missing:
						colour = '4'
					elif inside_extra:
						colour = '1'
					start += "\033[38;5;{}m{}\033[0m".format(colour, character)
				
				end = ''
				for mention in ends:
					character = ''
					if mention[1][0] and mention[1][1]:
						character = '}'
					elif mention[1][0]:
						character = ']'
					elif mention[1][1]:
						character = ')'
					inside_missing = False
					for emention in missing:
						if emention[1] <= mention[2][1] and mention[2][2] <= emention[2]:
							inside_missing = True
					inside_extra = False
					for emention in extra:
						if emention[1] <= mention[2][1] and mention[2][2] <= emention[2]:
							inside_extra = True
					colour = '15'
					if inside_missing and inside_extra:
						colour = '5'
					elif inside_missing:
						colour = '4'
					elif inside_extra:
						colour = '1'
					end += "\033[38;5;{}m{}\033[0m".format(colour, character)
				
				colour = '15'
				if len(extra) > 0 and len(missing) > 0:
					colour = '5'
				elif len(missing) > 0:
					colour = '4'
				elif len(extra) > 0:
					colour = '1'
				# head
				if (sentence, word) in heads:
					colour += ';4'
				text_word = start + "\033[38;5;{}m{}\033[0m".format(colour, text_word) + end
			output.append(text_word)
			word += 1
		print >> out, ' '.join(output) + '\n'
		sentence += 1

###if __name__ == "__main__":
###	print "Running doctest"
###	import doctest
###	doctest.testmod()

